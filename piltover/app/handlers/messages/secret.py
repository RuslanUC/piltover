from time import time

from loguru import logger
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.context import request_ctx
from piltover.db.enums import SecretUpdateType, FileType
from piltover.db.models import User, Peer, EncryptedChat, UserAuthorization, SecretUpdate, EncryptedFile, \
    UploadingFile, File
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import InputUser, InputUserFromMessage, EncryptedChatDiscarded, EncryptedFileEmpty, \
    InputEncryptedFileEmpty, InputEncryptedFile, InputEncryptedFileUploaded, InputEncryptedFileBigUploaded, \
    Long, InputEncryptedChat, LongVector
from piltover.tl.functions.messages import RequestEncryption, AcceptEncryption, DiscardEncryption, SendEncrypted, \
    SendEncryptedService, SendEncryptedFile, ReceivedQueue, SetEncryptedTyping, ReadEncryptedHistory
from piltover.tl.types.messages import SentEncryptedMessage, SentEncryptedFile
from piltover.utils import gen_safe_prime
from piltover.utils.gen_primes import CURRENT_DH_VERSION
from piltover.worker import MessageHandler

handler = MessageHandler("messages.secret")


def _check_g_a_or_b(g_a_or_b_bytes: bytes) -> bool:
    dh_p, dh_g = gen_safe_prime()
    g_a_or_b = int.from_bytes(g_a_or_b_bytes, "big")
    if not (1 < g_a_or_b < dh_p - 1):
        return False
    if not (2 ** (2048 - 64) < g_a_or_b < dh_p - 2 ** (2048 - 64)):
        return False
    return True


@handler.on_request(RequestEncryption, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def request_encryption(request: RequestEncryption, user: User):
    if not isinstance(request.user_id, (InputUser, InputUserFromMessage)):
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    if not _check_g_a_or_b(request.g_a):
        raise ErrorRpc(error_code=400, error_message="DH_G_A_INVALID")

    try:
        peer = await Peer.from_input_peer(user, request.user_id, False)
    except ErrorRpc as e:
        if e.error_message != "USER_ID_INVALID":
            logger.opt(exception=e).debug(f"Overriding rpc error from {e.error_message} to USER_ID_INVALID")
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    if not await UserAuthorization.filter(user=peer.user, allow_encrypted_requests=True).exists():
        return EncryptedChatDiscarded(id=0)

    # TODO: if chat with target user already exists, what do we do? discard?

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

    await upd.encryption_update(peer.user, chat)

    return chat.to_tl()


@handler.on_request(AcceptEncryption, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def accept_encryption(request: AcceptEncryption, user: User):
    if not _check_g_a_or_b(request.g_b):
        raise ErrorRpc(error_code=400, error_message="DH_G_B_INVALID")

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

    await upd.encryption_update(chat.from_user, chat)
    await upd.encryption_update(user, chat)

    return chat.to_tl()


@handler.on_request(DiscardEncryption, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def discard_encryption(request: DiscardEncryption, user: User):
    ctx = request_ctx.get()

    async with in_transaction():
        chat = await EncryptedChat.get_or_none(
            Q(from_user=user, from_sess__id=ctx.auth_id) | Q(to_user=user),
            id=request.chat_id,
        ).select_related("from_user", "to_user")

        if chat is None:
            raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ID_INVALID")

        if chat.to_user_id == user.id:
            if chat.to_sess_id is not None and chat.to_sess_id != ctx.auth_id:
                raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ALREADY_ACCEPTED")
        if chat.discarded:
            raise ErrorRpc(error_code=400, error_message="ENCRYPTION_ALREADY_DECLINED")

        chat.discarded = True
        chat.history_deleted = request.delete_history
        await chat.save(update_fields=["discarded", "history_deleted"])

    await upd.encryption_update(chat.from_user, chat)
    await upd.encryption_update(user, chat)

    return EncryptedChatDiscarded(id=request.chat_id, history_deleted=request.delete_history)


InputEncryptedFileT = (InputEncryptedFileEmpty | InputEncryptedFile | InputEncryptedFileUploaded
                       | InputEncryptedFileBigUploaded)


async def _get_secret_chat(peer: InputEncryptedChat, user: User) -> EncryptedChat:
    ctx = request_ctx.get()

    chat = await EncryptedChat.get_or_none(
        Q(from_user=user, from_sess=ctx.auth_id) | Q(to_user=user, to_sess=ctx.auth_id),
        id=peer.chat_id, access_hash=peer.access_hash,
    )

    if chat is None or chat.to_sess is None:
        raise ErrorRpc(error_code=400, error_message="CHAT_ID_INVALID")
    if chat.discarded:
        raise ErrorRpc(error_code=400, error_message="ENCRYPTION_DECLINED")

    return chat


async def _resolve_file(input_file: InputEncryptedFileT, user: User) -> EncryptedFile | None:
    if isinstance(input_file, InputEncryptedFileEmpty):
        return None

    ctx = request_ctx.get()

    if isinstance(input_file, (InputEncryptedFileUploaded, InputEncryptedFileBigUploaded)):
        uploaded_file = await UploadingFile.get_or_none(user=user, file_id=input_file.id)
        if uploaded_file is None:
            raise ErrorRpc(error_code=400, error_message="FILE_EMTPY")
        file = await uploaded_file.finalize_upload(
            ctx.storage, "application/vnd.encrypted", file_type=FileType.ENCRYPTED, force_fallback_mime=True,
        )
        return await EncryptedFile.create(file=file, key_fingerprint=input_file.key_fingerprint)

    if isinstance(input_file, InputEncryptedFile):
        if not File.check_access_hash(user.id, ctx.auth_id, input_file.id, input_file.access_hash):
            raise ErrorRpc(error_code=400, error_message="FILE_EMTPY")
        file = await EncryptedFile.get_or_none(
            file__id=input_file.id, file__type=FileType.ENCRYPTED,
        ).select_related("file")
        if file is None:
            raise ErrorRpc(error_code=400, error_message="FILE_EMTPY")

        return file

    raise RuntimeError("Unreachable")


async def _inc_qts(auth_id: int) -> UserAuthorization:
    async with in_transaction():
        auth = await UserAuthorization.select_for_update().get(id=auth_id)
        auth.upd_qts += 1
        await auth.save(update_fields=["upd_qts"])

    return auth


@handler.on_request(SendEncryptedFile, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(SendEncryptedService, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(SendEncrypted, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def send_encrypted(request: SendEncrypted | SendEncryptedService | SendEncryptedFile, user: User):
    chat = await _get_secret_chat(request.peer, user)

    file = None
    if isinstance(request, SendEncryptedFile):
        file = await _resolve_file(request.file, user)

    # TODO: check that request.data is valid (size-wise?)

    other_auth = await _inc_qts(chat.from_sess_id if chat.to_user_id == user.id else chat.to_sess_id)

    update = await SecretUpdate.create(
        qts=other_auth.upd_qts,
        type=SecretUpdateType.NEW_MESSAGE,
        authorization=other_auth,
        chat=chat,
        data=request.data,
        message_random_id=request.random_id,
        message_is_service=isinstance(request, SendEncryptedService),
        message_file=file,
    )

    await upd.send_encrypted_update(update)

    if isinstance(request, SendEncryptedFile):
        if file is None:
            resp_file = EncryptedFileEmpty()
        else:
            resp_file = file.to_tl()
        return SentEncryptedFile(date=int(update.date.timestamp()), file=resp_file)
    else:
        return SentEncryptedMessage(date=int(update.date.timestamp()))


@handler.on_request(ReceivedQueue, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def received_queue(request: ReceivedQueue):
    ctx = request_ctx.get()
    current_auth = await UserAuthorization.get_or_none(id=ctx.auth_id, user__id=ctx.user_id)

    if request.max_qts > current_auth.upd_qts or request.max_qts <= 0:
        raise ErrorRpc(error_code=400, error_message="MAX_QTS_INVALID")

    random_ids = await SecretUpdate.filter(
        authorization=current_auth, qts__lte=request.max_qts, message_random_id__not_isnull=True,
    ).values_list("message_random_id", flat=True)
    logger.trace(f"Removing {len(random_ids)}+ secret updates because of ReceivedQueue")
    logger.trace(f"Random ids btw: {random_ids!r}")
    await SecretUpdate.filter(authorization=current_auth, qts__lte=request.max_qts).delete()

    return LongVector(random_ids)


@handler.on_request(SetEncryptedTyping, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def set_encrypted_typing(request: SetEncryptedTyping, user: User):
    chat = await _get_secret_chat(request.peer, user)

    if request.typing:
        await upd.send_encrypted_typing(
            chat.id,
            chat.from_sess_id if user.id == chat.to_user_id else chat.to_sess_id,
        )

    return True


@handler.on_request(ReadEncryptedHistory, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def read_encrypted_history(request: ReadEncryptedHistory, user: User):
    chat = await _get_secret_chat(request.peer, user)

    if request.max_date > time():
        raise ErrorRpc(error_code=400, error_message="MAX_DATE_INVALID")

    other_auth = await _inc_qts(chat.from_sess_id if chat.to_user_id == user.id else chat.to_sess_id)

    update = await SecretUpdate.create(
        qts=other_auth.upd_qts,
        type=SecretUpdateType.HISTORY_READ,
        authorization=other_auth,
        chat=chat,
        data=Long.write(request.max_date),
    )

    await upd.send_encrypted_update(update)

    return True
