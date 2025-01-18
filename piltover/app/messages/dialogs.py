from datetime import datetime, UTC

from tortoise.expressions import Q

from piltover.app.updates import get_state_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType
from piltover.db.models import User, Dialog, Peer
from piltover.db.models.message import Message
from piltover.exceptions import ErrorRpc
from piltover.tl import InputPeerUser, InputPeerSelf, InputDialogPeer, InputPeerChat, DialogPeer
from piltover.tl.functions.messages import GetPeerDialogs, GetDialogs, GetPinnedDialogs, ReorderPinnedDialogs, \
    ToggleDialogPin, MarkDialogUnread, GetDialogUnreadMarks
from piltover.tl.types.messages import PeerDialogs, Dialogs
from piltover.worker import MessageHandler

handler = MessageHandler("messages.dialogs")


async def format_dialogs(user: User, dialogs: list[Dialog]) -> dict[str, list]:
    messages = []
    users = {}
    chats = {}

    for dialog in dialogs:
        message = await Message.filter(peer=dialog.peer).select_related("author", "peer").order_by("-id").first()
        if message is not None:
            messages.append(await message.to_tl(user))
            if message.author.id not in users:
                users[message.author.id] = await message.author.to_tl(user)

        if dialog.peer.peer_user(user) is not None and dialog.peer.peer_user(user).id not in users:
            users[dialog.peer.user.id] = await dialog.peer.peer_user(user).to_tl(user)
        if dialog.peer.type is PeerType.CHAT and dialog.peer.chat_id not in chats:
            #await dialog.peer.fetch_related("chat")
            chats[dialog.peer.chat.id] = await dialog.peer.chat.to_tl(user)
            for chat_user in await User.filter(chatparticipants__chat=dialog.peer.chat, id__not_in=list(users.keys())):
                users[chat_user.id] = await chat_user.to_tl(user)

    return {
        "dialogs": [await dialog.to_tl() for dialog in dialogs],
        "messages": messages,
        "chats": list(chats.values()),
        "users": list(users.values()),
    }


# noinspection PyUnusedLocal
async def get_dialogs_internal(
        peers: list[InputDialogPeer] | None, user: User, offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: InputPeerUser | InputPeerChat | None = None
) -> dict:
    query = Q(peer__owner=user)
    if offset_id:
        query &= Q(peer__messages__id__lt=offset_id)
    if offset_date:
        query &= Q(peer__messages__date__lt=datetime.fromtimestamp(offset_date, UTC))
    if offset_peer is not None:
        try:
            offset_peer = await Peer.from_input_peer_raise(user, offset_peer)
            peer_message_id = await Message.filter(peer=offset_peer).order_by("-id").first().values_list("id", flat=True)
            if peer_message_id is not None:
                query &= Q(peer__messages__id__lt=peer_message_id)
        except ErrorRpc:
            pass

    if peers is None:
        peers = []
    peers_query = None
    for peer in peers:
        if isinstance(peer.peer, InputPeerSelf):
            add_to_query = Q(peer__type=PeerType.SELF, peer__user=None)
        elif isinstance(peer.peer, InputPeerUser):
            add_to_query = Q(
                peer__type=PeerType.USER, peer__user__id=peer.peer.user_id, peer__access_hash=peer.peer.access_hash,
            )
        elif isinstance(peer.peer, InputPeerChat):
            add_to_query = Q(peer__type=PeerType.CHAT, peer__chat__id=peer.peer.chat_id)
        else:
            continue

        peers_query = add_to_query if peers_query is None else peers_query | add_to_query

    if peers_query is not None:
        query &= peers_query

    if limit > 100 or limit < 1:
        limit = 100

    dialogs = await Dialog.filter(query).select_related(
        "peer", "peer__owner", "peer__user", "peer__chat"
    ).order_by("-peer__messages__date").limit(limit)

    # TODO: return DialogsSlice if there is more than 100 dialogs ?
    return await format_dialogs(user, dialogs)


@handler.on_request(GetDialogs)
async def get_dialogs(request: GetDialogs, user: User):
    return Dialogs(**(await get_dialogs_internal(
        None, user, request.offset_id, request.offset_date, request.limit, request.offset_peer
    )))


@handler.on_request(GetPeerDialogs)
async def get_peer_dialogs(request: GetPeerDialogs, user: User):
    return PeerDialogs(
        **(await get_dialogs_internal(request.peers, user)),
        state=await get_state_internal(user)
    )


@handler.on_request(GetPinnedDialogs)
async def get_pinned_dialogs(user: User):
    dialogs = await Dialog.filter(peer__owner=user, pinned_index__not_isnull=True)\
        .select_related("peer", "peer__user", "peer__chat").order_by("-pinned_index")

    return PeerDialogs(
        **(await format_dialogs(user, dialogs)),
        state=await get_state_internal(user)
    )


@handler.on_request(ToggleDialogPin)
async def toggle_dialog_pin(request: ToggleDialogPin, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer.peer)) is None \
            or (dialog := await Dialog.get_or_none(peer=peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_HISTORY_EMPTY")

    if dialog.pinned_index:
        dialog.pinned_index = None
    else:
        dialog.pinned_index = await Dialog.filter(peer=peer, pinned_index__not_isnull=True).count()
        if dialog.pinned_index > 10:
            raise ErrorRpc(error_code=400, error_message="PINNED_DIALOGS_TOO_MUCH")

    await dialog.save(update_fields=["pinned_index"])
    await UpdatesManager.pin_dialog(user, peer)

    return True


@handler.on_request(ReorderPinnedDialogs)
async def reorder_pinned_dialogs(request: ReorderPinnedDialogs, user: User):
    pinned_now = await Dialog.filter(peer__owner=user, pinned_index__not_isnull=True).select_related("peer")
    pinned_now = {dialog.peer: dialog for dialog in pinned_now}
    pinned_after = []
    to_unpin: dict = pinned_now.copy() if request.force else {}

    for dialog_peer in request.order:
        if (peer := await Peer.from_input_peer(user, dialog_peer.peer)) is None:
            continue

        dialog = pinned_now.get(peer, None) or await Dialog.get_or_none(peer=peer).select_related("peer")
        if not dialog:
            continue

        pinned_after.append(dialog)
        to_unpin.pop(peer, None)

    if not request.force:
        pinned_after.extend(sorted(pinned_now.values(), key=lambda d: d.pinned_index))

    if to_unpin:
        unpin_ids = [dialog.id for dialog in to_unpin.values()]
        await Dialog.filter(id__in=unpin_ids).update(pinned_index=None)

    pinned_after.reverse()
    for idx, dialog in enumerate(pinned_after):
        dialog.pinned_index = idx

    if pinned_after:
        await Dialog.bulk_update(pinned_after, fields=["pinned_index"])
    await UpdatesManager.reorder_pinned_dialogs(user, pinned_after)

    return True


@handler.on_request(MarkDialogUnread)
async def mark_dialog_unread(request: MarkDialogUnread, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.peer.peer)
    if (dialog := await Dialog.get_or_none(peer=peer).select_related("peer")) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if dialog.unread_mark == request.unread:
        return True

    dialog.unread_mark = request.unread
    await dialog.save(update_fields=["unread_mark"])
    await UpdatesManager.update_dialog_unread_mark(user, dialog)

    return True


@handler.on_request(GetDialogUnreadMarks)
async def get_dialog_unread_marks(user: User) -> list[DialogPeer]:
    dialogs = await Dialog.filter(peer__owner=user, unread_mark=True).select_related("peer")

    return [
        DialogPeer(peer=dialog.peer.to_tl())
        for dialog in dialogs
    ]
