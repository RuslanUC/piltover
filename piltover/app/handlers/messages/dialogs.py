from datetime import datetime, UTC
from typing import cast

from tortoise.expressions import Q
from tortoise.functions import Max

from piltover.app.handlers.updates import get_state_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType
from piltover.db.models import User, Dialog, Peer, SavedDialog
from piltover.db.models._utils import resolve_users_chats
from piltover.db.models.message import Message
from piltover.exceptions import ErrorRpc
from piltover.tl import InputPeerUser, InputPeerSelf, InputPeerChat, DialogPeer
from piltover.tl.functions.messages import GetPeerDialogs, GetDialogs, GetPinnedDialogs, ReorderPinnedDialogs, \
    ToggleDialogPin, MarkDialogUnread, GetDialogUnreadMarks
from piltover.tl.types.messages import PeerDialogs, Dialogs, DialogsSlice
from piltover.worker import MessageHandler

handler = MessageHandler("messages.dialogs")


async def format_dialogs(
        user: User, dialogs: list[Dialog] | list[SavedDialog], allow_slicing: bool = False, folder_id: int | None = None
) -> dict[str, list]:
    messages = []

    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    for dialog in dialogs:
        message = await Message.filter(peer=dialog.peer).select_related("author", "peer").order_by("-id").first()
        if message is not None:
            messages.append(await message.to_tl(user))
            users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)
        else:
            users_q, chats_q, channels_q = Peer.query_users_chats_cls(dialog.peer_id, users_q, chats_q, channels_q)

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    result = {
        "dialogs": [await dialog.to_tl() for dialog in dialogs],
        "messages": messages,
        "chats": [*chats.values(), *channels.values()],
        "users": list(users.values()),
    }

    if not allow_slicing:
        return result

    # TODO: use folder_id in folder when archive will be added
    count = await Dialog.filter(peer__owner=user).count()
    if count > len(dialogs):
        result["count"] = count

    return result


class PeerWithDialogs(Peer):
    dialogs: Dialog | SavedDialog

    class Meta:
        abstract = True


async def get_dialogs_internal(
        model: type[Dialog | SavedDialog], user: User, offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: InputPeerUser | InputPeerChat | None = None, folder_id: int | None = None,
        exclude_pinned: bool = False, allow_slicing: bool = False,
) -> dict:
    if limit > 100 or limit < 1:
        limit = 100

    prefix = f"{model._meta.db_table}s"

    query = Q(**{f"{prefix}__peer__owner": user})

    if offset_peer is not None:
        input_peer = offset_peer
        offset_peer = peer_message_id = None
        try:
            offset_peer = await Peer.from_input_peer_raise(user, input_peer)
            peer_message_id = await Message.filter(peer=offset_peer).order_by("-id").first().values_list("id", flat=True)
        except ErrorRpc:
            pass

        peer_message_id = cast(int | None, peer_message_id)
        if peer_message_id is None:
            offset_id = 0
            if offset_peer is not None:
                query &= Q(id__lt=offset_peer.id)
        elif offset_id == 0 or offset_id > peer_message_id:
            offset_id = peer_message_id

    if offset_id:
        query &= Q(last_message_id__lt=offset_id)
    if exclude_pinned:
        query &= Q(**{f"{prefix}__pinned_index__isnull": True})
    date_annotation = {}
    if offset_date:
        date_annotation["last_message_date"] = Max("messages__date")
        query &= Q(last_message_date__lt=datetime.fromtimestamp(offset_date, UTC))

    # Doing it this way because, as far as i know, in Tortoise you cant reference outer-value from inner query
    #  and e.g. do something like
    #  Dialogs.annotate(last_message_id=Subquery(Message.filter(peer=F("peer")).order_by("-id").first().values_list("id", flat=True)))
    peers_with_dialogs = Peer.annotate(last_message_id=Max("messages__id"), **date_annotation)\
        .filter(query).limit(limit).order_by("-last_message_id", "-id")\
        .select_related("owner", "user", "chat", prefix)

    peer_with_dialog: PeerWithDialogs
    dialogs: list[Dialog | SavedDialog] = []

    async for peer_with_dialog in peers_with_dialogs:
        dialog = peer_with_dialog.dialogs
        dialog.peer = peer_with_dialog

        dialogs.append(dialog)

    return await format_dialogs(user, dialogs, allow_slicing, folder_id)


@handler.on_request(GetDialogs)
async def get_dialogs(request: GetDialogs, user: User):
    result = await get_dialogs_internal(
        Dialog, user, request.offset_id, request.offset_date, request.limit, request.offset_peer, request.folder_id,
        request.exclude_pinned, True
    )
    return Dialogs(**result) if "count" not in result else DialogsSlice(**result)


@handler.on_request(GetPeerDialogs)
async def get_peer_dialogs(request: GetPeerDialogs, user: User):
    query = Q(peer__owner=user)

    peers_query = None
    for peer in request.peers:
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

    if peers_query is None:
        return PeerDialogs(dialogs=[], messages=[], chats=[], users=[], state=await get_state_internal(user))

    query &= peers_query
    dialogs = await Dialog.filter(query).select_related("peer", "peer__owner", "peer__user", "peer__chat")

    return PeerDialogs(
        **(await format_dialogs(user, dialogs)),
        state=await get_state_internal(user),
    )


@handler.on_request(GetPinnedDialogs)
async def get_pinned_dialogs(request: GetPinnedDialogs, user: User):
    # TODO: get pinned dialogs from request.folder_id
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
