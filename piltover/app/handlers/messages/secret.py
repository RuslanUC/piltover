from loguru import logger
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.context import request_ctx
from piltover.db.enums import SecretUpdateType
from piltover.db.models import User, Peer, EncryptedChat, UserAuthorization, SecretUpdate
from piltover.exceptions import ErrorRpc
from piltover.tl import InputUser, InputUserFromMessage, EncryptedChatDiscarded
from piltover.tl.functions.messages import RequestEncryption, AcceptEncryption, DiscardEncryption, SendEncrypted, \
    SendEncryptedService
from piltover.tl.types.messages import SentEncryptedMessage
from piltover.utils import gen_safe_prime
from piltover.utils.gen_primes import CURRENT_DH_VERSION
from piltover.worker import MessageHandler

handler = MessageHandler("messages.secret")


@handler.on_request(RequestEncryption)
async def request_encryption(request: RequestEncryption, user: User):
    if not isinstance(request.user_id, (InputUser, InputUserFromMessage)):
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    dh_p, dh_g = gen_safe_prime()
    g_a = int.from_bytes(request.g_a, "big")
    if g_a >= dh_p:
        raise ErrorRpc(error_code=400, error_message="DH_G_A_INVALID")
    if (g_a % dh_g) != 0:
        raise ErrorRpc(error_code=400, error_message="DH_G_A_INVALID")

    # TODO: other checks like g_a size, etc.

    try:
        peer = await Peer.from_input_peer(user, request.user_id)
    except ErrorRpc as e:
        if e.error_message != "USER_ID_INVALID":
            logger.opt(exception=e).debug(f"Overriding rpc error from {e.error_message} to USER_ID_INVALID")
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    if not await UserAuthorization.filter(user=peer.user, allow_encrypted_requests=True).exists():
        return EncryptedChatDiscarded(id=0)

    ctx = request_ctx.get()
    chat = await EncryptedChat.create(
        from_user=user,
        from_sess=await UserAuthorization.get_or_none(id=ctx.auth_id, user__id=ctx.user_id),
        to_user=peer.user,
        to_sess=None,
        dh_version=CURRENT_DH_VERSION,
        g_a=request.g_a,
        g_b=b"",
    )

    await UpdatesManager.encryption_update(peer.user, chat)

    return await chat.to_tl(user, ctx.auth_id)


@handler.on_request(AcceptEncryption)
async def accept_encryption(request: AcceptEncryption, user: User):
    dh_p, dh_g = gen_safe_prime()
    g_b = int.from_bytes(request.g_b, "big")
    if g_b >= dh_p:
        raise ErrorRpc(error_code=400, error_message="DH_G_B_INVALID")
    if (g_b % dh_g) != 0:
        raise ErrorRpc(error_code=400, error_message="DH_G_B_INVALID")

    # TODO: other checks like g_b size, etc.

    async with in_transaction():
        chat = await EncryptedChat.select_for_update().get_or_none(
            id=request.peer.chat_id, access_hash=request.peer.access_hash, to_user=user,
        ).select_related("from_user")
        if chat is None:
            raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")

        if chat.to_sess_id is not None:
            raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ALREADY_ACCEPTED")
        if chat.discarded:
            raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ALREADY_DECLINED")

        ctx = request_ctx.get()
        current_auth = await UserAuthorization.get_or_none(id=ctx.auth_id, user__id=ctx.user_id)

        chat.g_b = request.g_b
        chat.to_sess = current_auth
        chat.to_sess_id = current_auth.id
        chat.key_fp = request.key_fingerprint
        await chat.save(update_fields=["g_b", "to_sess_id", "key_fp"])

    await UpdatesManager.encryption_update(chat.from_user, chat)
    await UpdatesManager.encryption_update(user, chat)

    return await chat.to_tl(user, ctx.auth_id)


@handler.on_request(DiscardEncryption)
async def discard_encryption(request: DiscardEncryption, user: User):
    async with in_transaction():
        chat = await EncryptedChat.select_for_update().get_or_none(id=request.chat_id, to_user=user)\
            .select_related("from_user")
        if chat is None:
            raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ID_INVALID")

        ctx = request_ctx.get()
        if chat.to_sess_id is not None and chat.to_sess_id != ctx.auth_id:
            raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ALREADY_ACCEPTED")
        if chat.discarded:
            raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ALREADY_DECLINED")

        chat.discarded = True
        chat.history_deleted = request.delete_history
        await chat.save(update_fields=["discarded", "history_deleted"])

    await UpdatesManager.encryption_update(chat.from_user, chat)
    await UpdatesManager.encryption_update(user, chat)

    return EncryptedChatDiscarded(id=request.chat_id, history_deleted=request.delete_history)


@handler.on_request(SendEncryptedService)
@handler.on_request(SendEncrypted)
async def send_encrypted(request: SendEncrypted | SendEncryptedService, user: User):
    ctx = request_ctx.get()

    chat_query = Q(
        Q(from_user=user, from_sess=ctx.auth_id) | Q(to_user=user, to_sess=ctx.auth_id),
        id=request.peer.chat_id, access_hash=request.peer.access_hash,
    )

    chat = await EncryptedChat.get_or_none(chat_query)
    if chat is None or chat.to_sess is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")
    if chat.discarded:
        raise ErrorRpc(error_code=400, error_message="ENCRYPTION_DECLINED")

    # TODO: check that request.data is valid (size-wise?)

    async with in_transaction():
        other_auth = await UserAuthorization.select_for_update().get(
            id=chat.from_sess_id if chat.to_user_id == user.id else chat.to_sess_id
        )

        other_auth.upd_qts += 1
        await other_auth.save(update_fields=["upd_qts"])

    update = await SecretUpdate.create(
        qts=other_auth.upd_qts,
        type=SecretUpdateType.NEW_MESSAGE,
        authorization=other_auth,
        chat=chat,
        data=request.data,
        message_random_id=request.random_id,
        message_is_service=isinstance(request, SendEncryptedService),
    )

    await UpdatesManager.send_encrypted(update)

    return SentEncryptedMessage(date=int(update.date.timestamp()))
