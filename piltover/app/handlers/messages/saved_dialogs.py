from datetime import datetime

from pytz import UTC
from tortoise.expressions import Q

from piltover.app.handlers.messages.dialogs import get_dialogs_internal, format_dialogs
from piltover.app.handlers.messages.history import get_messages_internal, format_messages_internal
import piltover.app.utils.updates_manager as upd
from piltover.db.enums import PeerType
from piltover.db.models import User, SavedDialog, Peer, State, MessageRef
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl.functions.messages import GetSavedDialogs, GetSavedHistory, DeleteSavedHistory, \
    GetPinnedSavedDialogs, ToggleSavedDialogPin, ReorderPinnedSavedDialogs
from piltover.tl.types.messages import SavedDialogs, Messages, AffectedHistory
from piltover.worker import MessageHandler

handler = MessageHandler("messages.saved_dialogs")


@handler.on_request(GetSavedDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_saved_dialogs(request: GetSavedDialogs, user: User) -> SavedDialogs:
    return SavedDialogs(
        **(await get_dialogs_internal(
            SavedDialog, user, request.offset_id, request.offset_date, request.limit, request.offset_peer
        ))
    )


@handler.on_request(GetSavedHistory, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_saved_history(request: GetSavedHistory, user: User) -> Messages:
    self_peer = await Peer.get(owner=user, type=PeerType.SELF)
    if self_peer is None:
        return Messages(messages=[], chats=[], users=[])

    peer = await Peer.from_input_peer_raise(user, request.peer)

    messages = await get_messages_internal(
        self_peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, saved_peer=peer
    )
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    return await format_messages_internal(
        user, messages, allow_slicing=True, peer=self_peer, saved_peer=peer, offset_id=request.offset_id,
    )


@handler.on_request(DeleteSavedHistory, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def delete_saved_history(request: DeleteSavedHistory, user: User) -> AffectedHistory:
    self_peer = await Peer.get(owner=user, type=PeerType.SELF)
    if self_peer is None:
        updates_state, _ = await State.get_or_create(user=user)
        return AffectedHistory(pts=updates_state.pts, pts_count=0, offset=0)

    peer = await Peer.from_input_peer_raise(user, request.peer)
    query = Q(peer=self_peer, content__fwd_header__saved_peer=peer)
    if request.max_id:
        query &= Q(id__lte=request.max_id)
    if request.max_date:
        query &= Q(content__date__lt=datetime.fromtimestamp(request.max_date, UTC))
    if request.min_date:
        query &= Q(content__date__gt=datetime.fromtimestamp(request.min_date, UTC))

    ids = await MessageRef.filter(query).order_by("-id").limit(1001).values_list("id", flat=True)
    if not ids:
        updates_state = await State.get(user=user)
        return AffectedHistory(pts=updates_state.pts, pts_count=0, offset=0)

    offset = 0
    if len(ids) > 1000:
        offset = ids.pop()

    await MessageRef.filter(id__in=ids).delete()
    pts = await upd.delete_messages(user, {user: ids})

    return AffectedHistory(pts=pts, pts_count=len(ids), offset=offset)


@handler.on_request(GetPinnedSavedDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_pinned_saved_dialogs(user: User) -> SavedDialogs:
    dialogs = await SavedDialog.filter(
        peer__owner=user, pinned_index__not_isnull=True,
    ).select_related("peer", "peer__user", "peer__chat").order_by("-pinned_index")

    return SavedDialogs(
        **(await format_dialogs(SavedDialog, user, dialogs))
    )


@handler.on_request(ToggleSavedDialogPin, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_saved_dialog_pin(request: ToggleSavedDialogPin, user: User) -> bool:
    if (dialog := await SavedDialog.get_or_none(peer__owner=user).select_related("peer")) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_HISTORY_EMPTY")

    if bool(dialog.pinned_index) == request.pinned:
        return True

    if request.pinned:
        # TODO: set pinned index to Max("pinned_index") + 1 instead of whatever this is
        dialog.pinned_index = await SavedDialog.filter(peer__owner=user, pinned_index__not_isnull=True).count()
    else:
        dialog.pinned_index = None

    await dialog.save(update_fields=["pinned_index"])
    await upd.pin_saved_dialog(user, dialog)

    return True


@handler.on_request(ReorderPinnedSavedDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def reorder_pinned_saved_dialogs(request: ReorderPinnedSavedDialogs, user: User):
    pinned_now = await SavedDialog.filter(
        peer__owner=user, pinned_index__not_isnull=True,
    ).select_related("peer", "peer__user")
    pinned_now = {dialog.peer: dialog for dialog in pinned_now}
    pinned_after = []
    to_unpin: dict = pinned_now.copy() if request.force else {}

    for dialog_peer in request.order:
        if (peer := await Peer.from_input_peer(user, dialog_peer.peer)) is None:
            continue

        dialog = pinned_now.get(peer, None)
        if dialog is None:
            dialog = await SavedDialog.get_or_none(peer=peer).select_related("peer", "peer__user")
        if not dialog:
            continue

        pinned_after.append(dialog)
        to_unpin.pop(peer, None)

    if not request.force:
        pinned_after.extend(sorted(pinned_now.values(), key=lambda d: d.pinned_index))

    if to_unpin:
        unpin_ids = [dialog.id for dialog in to_unpin.values()]
        await SavedDialog.filter(id__in=unpin_ids).update(pinned_index=None)

    pinned_after.reverse()
    for idx, dialog in enumerate(pinned_after):
        dialog.pinned_index = idx

    if pinned_after:
        await SavedDialog.bulk_update(pinned_after, fields=["pinned_index"])
    await upd.reorder_pinned_saved_dialogs(user, pinned_after)

    return True
