from datetime import datetime, UTC
from typing import cast, TypeVar

from tortoise.expressions import Q
from tortoise.functions import Max
from tortoise.queryset import QuerySet

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.updates import get_state_internal
from piltover.context import request_ctx
from piltover.db.enums import PeerType, DialogFolderId
from piltover.db.models import User, Dialog, Peer, SavedDialog, Chat, Channel, MessageRef
from piltover.db.models.peer import PeerOwnedT
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import InputPeerUser, InputPeerSelf, InputPeerChat, DialogPeer, Updates, TLObjectVector, \
    InputPeerChannel, InputDialogPeer
from piltover.tl.functions.folders import EditPeerFolders
from piltover.tl.functions.messages import GetPeerDialogs, GetDialogs, GetPinnedDialogs, ReorderPinnedDialogs, \
    ToggleDialogPin, MarkDialogUnread, GetDialogUnreadMarks
from piltover.tl.types.messages import PeerDialogs, Dialogs, DialogsSlice
from piltover.tl.base import InputPeer as TLInputPeerBase, Chat as TLChatBase
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("messages.dialogs")
DialogT = TypeVar("DialogT", Dialog, SavedDialog)


async def format_dialogs(
        model: type[DialogT], user_id: int, dialogs: list[DialogT], allow_slicing: bool = False,
        folder_id: int | None = None,
) -> dict[str, list]:
    result: dict

    if dialogs:
        ucc = UsersChatsChannels()

        dialog_by_peer: dict[tuple[PeerType, int], tuple[DialogT, MessageRef | None]] = {}
        for dialog in dialogs:
            dialog_by_peer[dialog.peer_key()] = (dialog, None)

        messages = await model.top_message_query_bulk(user_id, dialogs)
        for message_ref in messages:
            ucc.add_message(message_ref.content_id)
            peer_key = message_ref.peer_key()
            dialog, _ = dialog_by_peer[peer_key]
            dialog_by_peer[peer_key] = dialog, message_ref

        for dialog, message in dialog_by_peer.values():
            if message is not None:
                continue
            ucc.add_peer(dialog.peer)

        chats: list[TLChatBase]
        channels: list[TLChatBase]
        users, chats, channels = await ucc.resolve()

        result = {
            "dialogs": await model.to_tl_bulk(dialogs, dialog_by_peer),
            "messages": await MessageRef.to_tl_bulk_maybecached(messages, user_id),
            "chats": [*chats, *channels],
            "users": users,
        }
    else:
        result = {
            "dialogs": [],
            "messages": [],
            "chats": [],
            "users": [],
        }

    if not allow_slicing:
        return result

    dialogs_query = model.filter(peer__owner_id=user_id)
    if folder_id is not None and issubclass(model, Dialog):
        dialogs_query = dialogs_query.filter(folder_id=DialogFolderId(folder_id))
    count = await dialogs_query.count()
    if count > len(dialogs):
        result["count"] = count

    return result


class PeerWithDialogs(Peer):
    dialogs: Dialog | SavedDialog

    class Meta:
        abstract = True


async def get_dialogs_internal(
        model: type[DialogT], user_id: int, offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: TLInputPeerBase | None = None, folder_id: int | None = None,
        exclude_pinned: bool = False, allow_slicing: bool = False, only_visible: bool = True,
) -> dict:
    if limit > 100 or limit < 1:
        limit = 100

    prefix = f"{model._meta.db_table}s"

    query_filters: dict = {f"{prefix}__peer__owner_id": user_id}
    query = Q(**query_filters)

    if offset_peer is not None:
        input_peer = offset_peer
        offset_peer_id_filt = peer_message_id = None
        try:
            offset_peer_type, offset_peer_id = Peer.type_and_id_from_input_raise(user_id, input_peer)
        except ErrorRpc:
            pass
        else:
            offset_peer_id_query: QuerySet[Peer] = Peer.filter(owner_id=user_id)
            if offset_peer_type in (PeerType.SELF, PeerType.USER):
                peer_message_id_query = MessageRef.filter(peer__owner_id=user_id, peer__user_id=offset_peer_id)
                offset_peer_id_query = offset_peer_id_query.filter(user_id=offset_peer_id)
            elif offset_peer_type is PeerType.CHAT:
                peer_message_id_query = MessageRef.filter(peer__owner_id=user_id, peer__chat_id=offset_peer_id)
                offset_peer_id_query = offset_peer_id_query.filter(chat_id=offset_peer_id)
            elif offset_peer_type is PeerType.CHANNEL:
                peer_message_id_query = MessageRef.filter(peer__owner_id__isnull=True, peer__channel_id=offset_peer_id)
                offset_peer_id_query = offset_peer_id_query.filter(channel_id=offset_peer_id)
            else:
                raise Unreachable
            peer_message_id = cast(
                int | None, cast(
                    object, await peer_message_id_query.order_by("-id").first().values_list("id", flat=True)
                )
            )
            offset_peer_id_filt = cast(
                int | None, cast(
                    object, await offset_peer_id_query.first().values_list("id", flat=True)
                )
            )

        if peer_message_id is None:
            offset_id = 0
            if offset_peer_id_filt is not None:
                query &= Q(peer_id__lt=offset_peer_id_filt)
        elif offset_id == 0 or offset_id > peer_message_id:
            offset_id = peer_message_id

    if offset_id:
        query &= Q(last_message_id__lt=offset_id)
    if exclude_pinned:
        query_filters = {f"{prefix}__pinned_index__isnull": True}
        query &= Q(**query_filters)
    date_annotation = {}
    if offset_date:
        date_annotation["last_message_date"] = Max("messagerefs__content__date")
        query &= Q(last_message_date__lt=datetime.fromtimestamp(offset_date, UTC))
    if folder_id is not None and issubclass(model, Dialog):
        query &= Q(dialogs__folder_id=DialogFolderId(folder_id))
    if only_visible and issubclass(model, Dialog):
        query &= Q(dialogs__visible=True)

    # Doing it this way because, as far as i know, in Tortoise you cant reference outer-value from inner query
    #  and e.g. do something like
    #  Dialogs.annotate(last_message_id=Subquery(Message.filter(peer=F("peer")).order_by("-id").first().values_list("id", flat=True)))
    peers_with_dialogs_query: QuerySet[Peer] = Peer.annotate(last_message_id=Max("messagerefs__id"), **date_annotation)\
        .filter(query).limit(limit).order_by("-last_message_id", "-id")\
        .select_related("user", "chat", prefix)

    dialogs: list[DialogT] = []

    for peer_with_dialog in await peers_with_dialogs_query:
        dialog: DialogT = getattr(cast(PeerWithDialogs, peer_with_dialog), prefix)
        dialog.peer = peer_with_dialog
        dialogs.append(dialog)

    return await format_dialogs(model, user_id, dialogs, allow_slicing, folder_id)


@handler.on_request(GetDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_dialogs(request: GetDialogs, user_id: int) -> Dialogs | DialogsSlice:
    result = await get_dialogs_internal(
        Dialog, user_id, request.offset_id, request.offset_date, request.limit, request.offset_peer, request.folder_id,
        request.exclude_pinned, True, True,
    )
    return Dialogs(**result) if "count" not in result else DialogsSlice(**result)


@handler.on_request(GetPeerDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_peer_dialogs(request: GetPeerDialogs, user_id: int) -> PeerDialogs:
    auth_id = cast(int, request_ctx.get().auth_id)
    query = Q(peer__owner_id=user_id)

    peers_query = None
    for peer_dialog in request.peers:
        if not isinstance(peer_dialog, InputDialogPeer):
            continue

        peer = peer_dialog.peer

        # TODO: use Peer.type_and_id_from_input
        if isinstance(peer, InputPeerSelf):
            add_to_query = Q(peer__type=PeerType.SELF, peer__user=None)
        elif isinstance(peer, InputPeerUser):
            if not User.check_access_hash(user_id, auth_id, peer.user_id, peer.access_hash):
                continue
            add_to_query = Q(peer__type=PeerType.USER, peer__user_id=peer.user_id)
        elif isinstance(peer, InputPeerChat):
            add_to_query = Q(peer__type=PeerType.CHAT, peer__chat_id=Chat.norm_id(peer.chat_id))
        elif isinstance(peer, InputPeerChannel):
            channel_id = Channel.norm_id(peer.channel_id)
            if not Channel.check_access_hash(user_id, auth_id, channel_id, peer.access_hash):
                continue
            add_to_query = Q(peer__type=PeerType.CHANNEL, peer__channel_id=channel_id)
        else:
            continue

        peers_query = add_to_query if peers_query is None else peers_query | add_to_query

    if peers_query is None:
        return PeerDialogs(dialogs=[], messages=[], chats=[], users=[], state=await get_state_internal(user_id))

    query &= peers_query
    dialogs = await Dialog.filter(query).select_related("peer", "peer__user", "peer__chat")

    return PeerDialogs(
        **(await format_dialogs(Dialog, user_id, dialogs)),
        state=await get_state_internal(user_id),
    )


@handler.on_request(GetPinnedDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_pinned_dialogs(request: GetPinnedDialogs, user_id: int) -> PeerDialogs:
    dialogs = await Dialog.filter(
        peer__owner_id=user_id, pinned_index__not_isnull=True, folder_id=DialogFolderId(request.folder_id), visible=True
    ).select_related("peer", "peer__user", "peer__chat").order_by("-pinned_index")

    return PeerDialogs(
        **(await format_dialogs(Dialog, user_id, dialogs)),
        state=await get_state_internal(user_id)
    )


@handler.on_request(ToggleDialogPin, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_dialog_pin(request: ToggleDialogPin, user_id: int):
    if not isinstance(request.peer, InputDialogPeer):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if (peer := await Peer.from_input_peer(user_id, request.peer.peer)) is None \
            or (dialog := await Dialog.get_or_none(peer=peer, visible=True)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_HISTORY_EMPTY")

    if bool(dialog.pinned_index) == request.pinned:
        return True

    if request.pinned:
        max_index = cast(
            int | None,
            await Dialog.filter(
                peer=peer, folder_id=dialog.folder_id, visible=True,
            ).annotate(max_pinned_index=Max("pinned_index")).first().values_list("max_pinned_index", flat=True)
        )
        dialog.pinned_index = (max_index or -1) + 1
        if dialog.pinned_index > 10:
            raise ErrorRpc(error_code=400, error_message="PINNED_DIALOGS_TOO_MUCH")
    else:
        dialog.pinned_index = None

    await dialog.save(update_fields=["pinned_index"])
    await upd.pin_dialog(user_id, peer, dialog)

    return True


@handler.on_request(ReorderPinnedDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def reorder_pinned_dialogs(request: ReorderPinnedDialogs, user_id: int):
    pinned_now = {
        dialog.peer: dialog
        for dialog in await Dialog.filter(
            peer__owner_id=user_id, pinned_index__not_isnull=True, folder_id=DialogFolderId(request.folder_id),
            visible=True
        ).select_related("peer")
    }
    pinned_after = []
    to_unpin: dict = pinned_now.copy() if request.force else {}
    folder_id = DialogFolderId(request.folder_id)

    for dialog_peer in request.order:
        if not isinstance(dialog_peer, InputDialogPeer):
            continue

        if (peer := await Peer.from_input_peer(user_id, dialog_peer.peer)) is None:
            continue

        dialog = pinned_now.get(peer, None)
        if dialog is None:
            dialog = await Dialog.get_or_none(peer=peer, folder_id=folder_id, visible=True).select_related("peer")
        if not dialog:
            continue

        pinned_after.append(dialog)
        to_unpin.pop(peer, None)

    if not request.force:
        pinned_after.extend(sorted(pinned_now.values(), key=lambda d: d.pinned_index or 0))

    if to_unpin:
        unpin_ids = [dialog.id for dialog in to_unpin.values()]
        await Dialog.filter(id__in=unpin_ids).update(pinned_index=None)

    pinned_after.reverse()
    for idx, dialog in enumerate(pinned_after):
        dialog.pinned_index = idx

    if pinned_after:
        await Dialog.bulk_update(pinned_after, fields=["pinned_index"])
    await upd.reorder_pinned_dialogs(user_id, pinned_after)

    return True


@handler.on_request(MarkDialogUnread, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def mark_dialog_unread(request: MarkDialogUnread, user_id: int) -> bool:
    if not isinstance(request.peer, InputDialogPeer):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    peer_query = Peer.query_from_input_peer(user_id, request.peer.peer, True, False)
    if peer_query is None or (peer := await peer_query) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    if (dialog := await Dialog.get_or_none(peer=peer, visible=True)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if dialog.unread_mark == request.unread:
        return True

    dialog.peer = peer
    dialog.unread_mark = request.unread
    await dialog.save(update_fields=["unread_mark"])
    await upd.update_dialog_unread_mark(user_id, dialog)

    return True


@handler.on_request(GetDialogUnreadMarks, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_dialog_unread_marks(user_id: int) -> TLObjectVector[DialogPeer]:
    peers: list[PeerOwnedT] = await Peer.filter(owner_id=user_id, dialogs__unread_mark=True, dialogs__visible=True)

    return TLObjectVector([
        DialogPeer(peer=peer.to_tl())
        for peer in peers
    ])


@handler.on_request(EditPeerFolders, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def edit_peer_folders(request: EditPeerFolders, user_id: int) -> Updates:
    updated_dialogs = []

    for folder_peer in request.folder_peers:
        if folder_peer.folder_id not in DialogFolderId._value2member_map_:
            raise ErrorRpc(error_code=400, error_message="FOLDER_ID_INVALID")
        if (peer := await Peer.from_input_peer(user_id, folder_peer.peer)) is None \
                or (dialog := await Dialog.get_or_none(peer=peer, visible=True)) is None:
            continue

        new_folder_id = DialogFolderId(folder_peer.folder_id)
        if dialog.folder_id == new_folder_id:
            continue

        dialog.peer = peer
        dialog.folder_id = new_folder_id
        updated_dialogs.append(dialog)

    await Dialog.bulk_update(updated_dialogs, ["folder_id"])
    return await upd.update_folder_peers(user_id, updated_dialogs)
