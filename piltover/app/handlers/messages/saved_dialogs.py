from datetime import datetime

from pytz import UTC
from tortoise.expressions import Q

from piltover.app.handlers.messages.dialogs import get_dialogs_query, format_dialogs
from piltover.app.handlers.messages.history import get_messages_internal, format_messages_internal
from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType
from piltover.db.models import User, SavedDialog, Peer, State, Message
from piltover.tl import InputPeerUser, InputPeerChat
from piltover.tl.functions.messages import GetSavedDialogs, GetSavedHistory, DeleteSavedHistory
from piltover.tl.types.messages import SavedDialogs, Messages, AffectedHistory
from piltover.worker import MessageHandler

handler = MessageHandler("messages.saved_dialogs")


async def get_saved_dialogs_internal(
        user: User, offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: InputPeerUser | InputPeerChat | None = None
) -> dict:
    query = await get_dialogs_query(None, user, offset_id, offset_date, offset_peer)

    if limit > 100 or limit < 1:
        limit = 100

    dialogs = await SavedDialog.filter(query).select_related(
        "peer", "peer__owner", "peer__user", "peer__chat"
    ).order_by("-peer__messages__date").limit(limit)

    # TODO: return SavedDialogsSlice if there is more than 100 dialogs ?
    return await format_dialogs(user, dialogs)


@handler.on_request(GetSavedDialogs)
async def get_saved_dialogs(request: GetSavedDialogs, user: User) -> SavedDialogs:
    return SavedDialogs(
        **(await get_saved_dialogs_internal(
            user, request.offset_id, request.offset_date, request.limit, request.offset_peer
        ))
    )


@handler.on_request(GetSavedHistory)
async def get_saved_history(request: GetSavedHistory, user: User) -> Messages:
    self_peer = await Peer.get_or_none(owner=user, type=PeerType.SELF)
    if self_peer is None:
        return Messages(messages=[], chats=[], users=[])

    peer = await Peer.from_input_peer_raise(user, request.peer)

    messages = await get_messages_internal(
        self_peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, saved_peer=peer
    )
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    return await format_messages_internal(user, messages)


@handler.on_request(DeleteSavedHistory)
async def delete_messages(request: DeleteSavedHistory, user: User):
    self_peer = await Peer.get_or_none(owner=user, type=PeerType.SELF)
    if self_peer is None:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedHistory(pts=updates_state.pts, pts_count=0, offset=0)

    peer = await Peer.from_input_peer_raise(user, request.peer)
    query = Q(peer=self_peer, fwd_header__saved_peer=peer)
    if request.max_id:
        query &= Q(id__lte=request.max_id)
    if request.max_date:
        query &= Q(date__lt=datetime.fromtimestamp(request.max_date, UTC))
    if request.min_date:
        query &= Q(date__gt=datetime.fromtimestamp(request.min_date, UTC))

    ids = await Message.filter(query).values_list("id", flat=True)
    if not ids:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedHistory(pts=updates_state.pts, pts_count=0, offset=0)

    await Message.filter(id__in=ids).delete()
    pts = await UpdatesManager.delete_messages(user, {user: ids})

    return AffectedHistory(pts=pts, pts_count=len(ids), offset=0)


# TODO: GetPinnedSavedDialogs
# TODO: ToggleSavedDialogPin
# TODO: ReorderPinnedSavedDialogs
