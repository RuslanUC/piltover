from datetime import datetime, UTC
from typing import cast, TypeVar, overload, Literal

from pypika_tortoise import Dialects, Parameter
from tortoise import Tortoise
from tortoise.expressions import Q
from tortoise.functions import Max
from tortoise.queryset import QuerySet

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.updates import get_state_internal
from piltover.db.enums import PeerType, DialogFolderId
from piltover.db.models import Dialog, Peer, SavedDialog, MessageRef, MessageDraft, PeerNotifySettings, MessageContent
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import DialogPeer, Updates, TLObjectVector, InputDialogPeer
from piltover.tl.base import InputPeer as TLInputPeerBase, Chat as TLChatBase, DialogPeer as TLDialogPeerBase
from piltover.tl.functions.folders import EditPeerFolders
from piltover.tl.functions.messages import GetPeerDialogs, GetDialogs, GetPinnedDialogs, ReorderPinnedDialogs, \
    ToggleDialogPin, MarkDialogUnread, GetDialogUnreadMarks
from piltover.tl.types.messages import PeerDialogs, Dialogs, DialogsSlice, SavedDialogs, SavedDialogsSlice
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("messages.dialogs")
DialogT = TypeVar("DialogT", Dialog, SavedDialog)
TLDialogsT = TypeVar("TLDialogsT", Dialogs, SavedDialogs)
TLDialogsSliceT = TypeVar("TLDialogsSliceT", DialogsSlice, SavedDialogsSlice)


@overload
async def format_dialogs(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        dialogs: list[DialogT], allow_slicing: Literal[False] = False, folder_id: int | None = None,
) -> TLDialogsT:
    ...


@overload
async def format_dialogs(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        dialogs: list[DialogT], allow_slicing: Literal[True] = True, folder_id: int | None = None,
) -> TLDialogsT | TLDialogsSliceT:
    ...


@overload
async def format_dialogs(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        dialogs: list[DialogT], allow_slicing: bool = False, folder_id: int | None = None,
) -> TLDialogsT | TLDialogsSliceT:
    ...


async def format_dialogs(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        dialogs: list[DialogT], allow_slicing: bool = False, folder_id: int | None = None,
) -> TLDialogsT | TLDialogsSliceT:
    result: TLDialogsT | TLDialogsSliceT

    if dialogs:
        ucc = UsersChatsChannels()

        dialog_by_peer: dict[int, tuple[DialogT, MessageRef | None]] = {}
        for dialog in dialogs:
            dialog_by_peer[dialog.peer_id] = (dialog, None)

        messages = await model.top_message_query_bulk(user_id, dialogs)
        for message_ref in messages:
            dialog, _ = dialog_by_peer[message_ref.peer_id]
            dialog_by_peer[message_ref.peer_id] = dialog, message_ref

        for dialog, message in dialog_by_peer.values():
            if message is not None:
                continue
            ucc.add_peer(dialog.peer)

        tl_messages = await MessageRef.to_tl_bulk_maybecached(messages, user_id, False)
        for tl_message in tl_messages:
            ucc.add_from_tl(tl_message)

        chats: list[TLChatBase]
        channels: list[TLChatBase]
        users, chats, channels = await ucc.resolve()

        result = tl_cls(
            dialogs=await model.to_tl_bulk(user_id, dialogs, dialog_by_peer),
            messages=tl_messages,
            chats=[*chats, *channels],
            users=users,
        )
    else:
        result = tl_cls(
            dialogs=[],
            messages=[],
            chats=[],
            users=[],
        )

    if not allow_slicing:
        return result

    dialogs_query = model.filter(owner_id=user_id)
    if folder_id is not None and issubclass(model, Dialog):
        dialogs_query = dialogs_query.filter(folder_id=DialogFolderId(folder_id))
    if issubclass(model, Dialog):
        dialogs_query = dialogs_query.filter(visible=True)
    count = await dialogs_query.count()
    if count > len(dialogs):
        return tl_slice_cls(
            dialogs=result.dialogs,
            messages=result.messages,
            chats=result.chats,
            users=result.users,
            count=count,
        )

    return result


@overload
async def get_dialogs_internal(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: TLInputPeerBase | None = None, folder_id: int | None = None,
        exclude_pinned: bool = False, allow_slicing: Literal[False] = False,
) -> TLDialogsT:
    ...


@overload
async def get_dialogs_internal(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: TLInputPeerBase | None = None, folder_id: int | None = None,
        exclude_pinned: bool = False, allow_slicing: Literal[True] = True,
) -> TLDialogsT | TLDialogsSliceT:
    ...


@overload
async def get_dialogs_internal(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: TLInputPeerBase | None = None, folder_id: int | None = None,
        exclude_pinned: bool = False, allow_slicing: bool = False,
) -> TLDialogsT | TLDialogsSliceT:
    ...


async def _get_Dialog_dialogs_internal(
        user_id: int, offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: TLInputPeerBase | None = None, folder_id: int | None = None,
        exclude_pinned: bool = False, allow_slicing: bool = False,
) -> Dialogs | DialogsSlice:
    conn = Tortoise.get_connection("default")
    dialect = Dialects(conn.capabilities.dialect)
    placeholder_factory = Parameter.IDX_PLACEHOLDERS[dialect]

    add_condition = []
    params = []

    # TODO: offset peer

    if offset_id:
        add_condition.append(f"dp.last_message_id < {placeholder_factory(len(params) + 2)}")
        params.append(offset_id)
    if exclude_pinned:
        add_condition.append("d.pinned_index IS NULL")
    if offset_date:
        add_condition.append(f"dp.last_message_date < {placeholder_factory(len(params) + 2)}")
        params.append(datetime.fromtimestamp(offset_date, UTC))
    if folder_id is not None:
        add_condition.append(f"d.folder_id = {placeholder_factory(len(params) + 2)}")
        params.append(folder_id)

    if add_condition:
        add_condition.insert(0, "")

    dialogs_dicts = await conn.execute_query_dict(
        f"""
        SELECT 
            d.id `dialog.id`,
            d.pinned_index `dialog.pinned_index`,
            d.owner_id `dialog.owner_id`,
            d.peer_id `dialog.peer_id`,
            d.unread_mark `dialog.unread_mark`,
            d.folder_id `dialog.folder_id`,
            d.visible `dialog.visible`,
            d.last_read_message_id `dialog.last_read_message_id`,
            
            dp.id `peer.id`,
            dp.owner_id `peer.owner_id`,
            dp.type `peer.type`,
            dp.blocked_at `peer.blocked_at`,
            dp.user_ttl_period_days `peer.user_ttl_period_days`,
            dp.user_has_wallpaper `peer.user_has_wallpaper`,
            dp.last_message_id `peer.last_message_id`,
            dp.last_message_date `peer.last_message_date`,
            dp.out_max_read_id `peer.out_max_read_id`,
            dp.user_id `peer.user_id`,
            dp.chat_id `peer.chat_id`,
            dp.channel_id `peer.channel_id`,
            
            draft.id `draft.id`,
            draft.message `draft.message`,
            draft.date `draft.date`,
            draft.reply_to_id `draft.reply_to_id`,
            draft.no_webpage `draft.no_webpage`,
            draft.invert_media `draft.invert_media`,
            draft.entities `draft.entities`,
            
            notif.id `notif.id`,
            notif.show_previews `notif.show_previews`,
            notif.muted `notif.muted`,
            notif.muted_until `notif.muted_until`,
            
            top_ref.id `top_ref.id`,
            top_ref.content_id `top_ref.content_id`,
            top_ref.peer_id `top_ref.peer_id`,
            top_ref.random_id `top_ref.random_id`,
            top_ref.random_user_id `top_ref.random_user_id`,
            top_ref.pinned `top_ref.pinned`,
            top_ref.version `top_ref.version`,
            top_ref.from_scheduled `top_ref.from_scheduled`,
            top_ref.reply_to_id `top_ref.reply_to_id`,
            top_ref.top_message_id `top_ref.top_message_id`,
            top_ref.discussion_id `top_ref.discussion_id`,
            top_ref.is_discussion `top_ref.is_discussion`,
            top_ref.scheduled_by_user_id `top_ref.scheduled_by_user_id`,
            top_ref.author_id_for_unread_reactions `top_ref.author_id_for_unread_reactions`,
            top_ref.reactions_unread_author_id `top_ref.reactions_unread_author_id`,
            
            top_content.id `top_content.id`,
            top_content.message `top_content.message`,
            top_content.date `top_content.date`,
            top_content.edit_date `top_content.edit_date`,
            top_content.type `top_content.type`,
            top_content.entities `top_content.entities`,
            top_content.extra_info `top_content.extra_info`,
            top_content.media_group_id `top_content.media_group_id`,
            top_content.channel_post `top_content.channel_post`,
            top_content.anonymous `top_content.anonymous`,
            top_content.post_author `top_content.post_author`,
            top_content.scheduled_date `top_content.scheduled_date`,
            top_content.ttl_period_days `top_content.ttl_period_days`,
            top_content.reply_markup `top_content.reply_markup`,
            top_content.no_forwards `top_content.no_forwards`,
            top_content.edit_hide `top_content.edit_hide`,
            top_content.author_id `top_content.author_id`,
            top_content.media_id `top_content.media_id`,
            top_content.fwd_header_id `top_content.fwd_header_id`,
            top_content.post_info_id `top_content.post_info_id`,
            top_content.via_bot_id `top_content.via_bot_id`,
            top_content.version `top_content.version`,
            top_content.reactions_version `top_content.reactions_version`,
            top_content.replies_version `top_content.replies_version`,
            top_content.send_as_channel_id `top_content.send_as_channel_id`,
            top_content.internal_random_id `top_content.internal_random_id`,
            top_content.can_see_reactions_list `top_content.can_see_reactions_list`,
            top_content.reply_quote_text `top_content.reply_quote_text`,
            top_content.reply_quote_offset `top_content.reply_quote_offset`,
            
            COUNT(unread_message.id) `_.unread_count`,
            COUNT(unread_reactions.id) `_.unread_reactions_count`
        FROM dialog d
            INNER JOIN peer dp ON d.peer_id = dp.id
            LEFT OUTER JOIN messagedraft draft ON draft.user_id = d.owner_id AND draft.peer_id = d.peer_id
            LEFT OUTER JOIN peernotifysettings notif ON notif.user_id = d.owner_id AND notif.peer_id = d.peer_id
            LEFT OUTER JOIN messageref top_ref ON top_ref.id = dp.last_message_id
            LEFT OUTER JOIN messagecontent top_content ON top_content.id = top_ref.content_id
            JOIN messageref unread_message ON d.peer_id = unread_message.peer_id AND unread_message.id > d.last_read_message_id AND unread_message.scheduled_by_user_id IS NULL
            JOIN messageref unread_reactions ON d.peer_id = unread_message.peer_id AND unread_reactions.reactions_unread_author_id = {placeholder_factory(1)}
        WHERE d.owner_id = {placeholder_factory(2)} AND d.visible = 1 {' AND '.join(add_condition)}
        GROUP BY d.peer_id
        ORDER BY `peer.last_message_date` DESC, `peer.last_message_id` DESC, `peer.id` DESC
        LIMIT {placeholder_factory(len(params) + 3)}
        """,
        [user_id, user_id, *params, limit],
    )

    if dialogs_dicts:
        dialogs = []
        drafts = []
        notify_settings = []
        unread_counts = []
        unread_reaction_counts = []
        messages = []

        for dialog_dict in dialogs_dicts:
            peer = Peer(
                id=dialog_dict["peer.id"],
                owner_id=dialog_dict["peer.owner_id"],
                type=dialog_dict["peer.type"],
                blocked_at=dialog_dict["peer.blocked_at"],
                user_ttl_period_days=dialog_dict["peer.user_ttl_period_days"],
                user_has_wallpaper=dialog_dict["peer.user_has_wallpaper"],
                last_message_id=dialog_dict["peer.last_message_id"],
                last_message_date=dialog_dict["peer.last_message_date"],
                out_max_read_id=dialog_dict["peer.out_max_read_id"],
                user_id=dialog_dict["peer.user_id"],
                chat_id=dialog_dict["peer.chat_id"],
                channel_id=dialog_dict["peer.channel_id"],
            )
            peer._saved_in_db = True

            dialogs.append(dialog := Dialog(
                id=dialog_dict["dialog.id"],
                pinned_index=dialog_dict["dialog.pinned_index"],
                owner_id=dialog_dict["dialog.owner_id"],
                peer_id=dialog_dict["dialog.peer_id"],
                unread_mark=dialog_dict["dialog.unread_mark"],
                folder_id=dialog_dict["dialog.folder_id"],
                visible=dialog_dict["dialog.visible"],
                last_read_message_id=dialog_dict["dialog.last_read_message_id"],

                peer=peer,
            ))
            dialog._saved_in_db = True

            if dialog_dict["draft.id"] is None:
                drafts.append(None)
            else:
                drafts.append(MessageDraft(
                    id=dialog_dict["draft.id"],
                    message=dialog_dict["draft.message"],
                    date=dialog_dict["draft.date"],
                    reply_to_id=dialog_dict["draft.reply_to_id"],
                    no_webpage=dialog_dict["draft.no_webpage"],
                    invert_media=dialog_dict["draft.invert_media"],
                    entities=dialog_dict["draft.entities"],
                ))

            if dialog_dict["notif.id"] is None:
                notify_settings.append(None)
            else:
                notify_settings.append(PeerNotifySettings(
                    id=dialog_dict["notif.id"],
                    show_previews=dialog_dict["notif.show_previews"],
                    muted=dialog_dict["notif.muted"],
                    muted_until=dialog_dict["notif.muted_until"],
                ))

            unread_counts.append(dialog_dict["_.unread_count"])
            unread_reaction_counts.append(dialog_dict["_.unread_reactions_count"])

            if dialog_dict["top_ref.id"] is not None:
                messages.append(ref := MessageRef(
                    id=dialog_dict["top_ref.id"],
                    content_id=dialog_dict["top_ref.content_id"],
                    peer_id=dialog_dict["top_ref.peer_id"],
                    random_id=dialog_dict["top_ref.random_id"],
                    random_user_id=dialog_dict["top_ref.random_user_id"],
                    pinned=dialog_dict["top_ref.pinned"],
                    version=dialog_dict["top_ref.version"],
                    from_scheduled=dialog_dict["top_ref.from_scheduled"],
                    reply_to_id=dialog_dict["top_ref.reply_to_id"],
                    top_message_id=dialog_dict["top_ref.top_message_id"],
                    discussion_id=dialog_dict["top_ref.discussion_id"],
                    is_discussion=dialog_dict["top_ref.is_discussion"],
                    scheduled_by_user_id=dialog_dict["top_ref.scheduled_by_user_id"],
                    author_id_for_unread_reactions=dialog_dict["top_ref.author_id_for_unread_reactions"],
                    reactions_unread_author_id=dialog_dict["top_ref.reactions_unread_author_id"],
                ))
                ref._saved_in_db = True

                content = MessageContent(
                    id=dialog_dict["top_content.id"],
                    message=dialog_dict["top_content.message"],
                    date=dialog_dict["top_content.date"],
                    edit_date=dialog_dict["top_content.edit_date"],
                    type=dialog_dict["top_content.type"],
                    entities=dialog_dict["top_content.entities"],
                    extra_info=dialog_dict["top_content.extra_info"],
                    media_group_id=dialog_dict["top_content.media_group_id"],
                    channel_post=dialog_dict["top_content.channel_post"],
                    anonymous=dialog_dict["top_content.anonymous"],
                    post_author=dialog_dict["top_content.post_author"],
                    scheduled_date=dialog_dict["top_content.scheduled_date"],
                    ttl_period_days=dialog_dict["top_content.ttl_period_days"],
                    reply_markup=dialog_dict["top_content.reply_markup"],
                    no_forwards=dialog_dict["top_content.no_forwards"],
                    edit_hide=dialog_dict["top_content.edit_hide"],
                    author_id=dialog_dict["top_content.author_id"],
                    media_id=dialog_dict["top_content.media_id"],
                    fwd_header_id=dialog_dict["top_content.fwd_header_id"],
                    post_info_id=dialog_dict["top_content.post_info_id"],
                    via_bot_id=dialog_dict["top_content.via_bot_id"],
                    version=dialog_dict["top_content.version"],
                    reactions_version=dialog_dict["top_content.reactions_version"],
                    replies_version=dialog_dict["top_content.replies_version"],
                    send_as_channel_id=dialog_dict["top_content.send_as_channel_id"],
                    internal_random_id=dialog_dict["top_content.internal_random_id"],
                    can_see_reactions_list=dialog_dict["top_content.can_see_reactions_list"],
                    reply_quote_text=dialog_dict["top_content.reply_quote_text"],
                    reply_quote_offset=dialog_dict["top_content.reply_quote_offset"],
                )
                content._saved_in_db = True
                ref.content = content

        ucc = UsersChatsChannels()

        dialog_by_peer: dict[int, tuple[Dialog, MessageRef | None]] = {}
        for dialog in dialogs:
            dialog_by_peer[dialog.peer_id] = (dialog, None)

        # messages = await Dialog.top_message_query_bulk(user_id, dialogs)
        for message_ref in messages:
            dialog, _ = dialog_by_peer[message_ref.peer_id]
            dialog_by_peer[message_ref.peer_id] = dialog, message_ref

        for dialog, message in dialog_by_peer.values():
            if message is not None:
                continue
            ucc.add_peer(dialog.peer)

        tl_messages = await MessageRef.to_tl_bulk_maybecached(messages, user_id, False)
        for tl_message in tl_messages:
            ucc.add_from_tl(tl_message)

        chats: list[TLChatBase]
        channels: list[TLChatBase]
        users, chats, channels = await ucc.resolve()

        result = Dialogs(
            dialogs=await Dialog.to_tl_bulk(user_id, dialogs, dialog_by_peer, drafts, notify_settings, unread_counts, unread_reaction_counts),
            messages=tl_messages,
            chats=[*chats, *channels],
            users=users,
        )
    else:
        dialogs = []
        result = Dialogs(
            dialogs=[],
            messages=[],
            chats=[],
            users=[],
        )

    if not allow_slicing:
        return result

    dialogs_query = Dialog.filter(owner_id=user_id, visible=True)
    if folder_id is not None:
        dialogs_query = dialogs_query.filter(folder_id=DialogFolderId(folder_id))
    count = await dialogs_query.count()
    if count > len(dialogs):
        return DialogsSlice(
            dialogs=result.dialogs,
            messages=result.messages,
            chats=result.chats,
            users=result.users,
            count=count,
        )

    return result


async def get_dialogs_internal(
        model: type[DialogT], tl_cls: type[TLDialogsT], tl_slice_cls: type[TLDialogsSliceT], user_id: int,
        offset_id: int = 0, offset_date: int = 0, limit: int = 100,
        offset_peer: TLInputPeerBase | None = None, folder_id: int | None = None,
        exclude_pinned: bool = False, allow_slicing: bool = False,
) -> TLDialogsT | TLDialogsSliceT:
    if limit > 100 or limit < 1:
        limit = 100

    if model is Dialog:
        return await _get_Dialog_dialogs_internal(
            user_id, offset_id, offset_date, limit, offset_peer, folder_id, exclude_pinned, allow_slicing,
        )

    query = Q(owner_id=user_id)

    if offset_peer is not None:
        offset_peer_: Peer | None = None
        peer_message_id: int | None = None
        try:
            offset_peer_type, offset_peer_id = Peer.type_and_id_from_input_raise(user_id, offset_peer)
        except ErrorRpc:
            pass
        else:
            offset_peer_query: QuerySet[Peer] = Peer.filter()
            if offset_peer_type in (PeerType.SELF, PeerType.USER):
                offset_peer_query = offset_peer_query.filter(user_id=offset_peer_id)
            elif offset_peer_type is PeerType.CHAT:
                offset_peer_query = offset_peer_query.filter(chat_id=offset_peer_id)
            elif offset_peer_type is PeerType.CHANNEL:
                offset_peer_query = offset_peer_query.filter(channel_id=offset_peer_id)
            else:
                raise Unreachable
            if offset_peer_type is not PeerType.CHANNEL:
                offset_peer_query = offset_peer_query.filter(owner_id=user_id)
            offset_peer_ = await offset_peer_query.get_or_none().only("id", "last_message_id")
            if offset_peer_ is not None:
                peer_message_id = offset_peer_.last_message_id

        if peer_message_id is None:
            offset_id = 0
            if offset_peer_ is not None:
                query &= Q(peer_id__lt=offset_peer_.id)
        elif offset_id == 0 or offset_id > peer_message_id:
            offset_id = peer_message_id

    if offset_id:
        query &= Q(peer__last_message_id__lt=offset_id)
    if exclude_pinned:
        query &= Q(pinned_index__isnull=True)
    if offset_date:
        query &= Q(peer__last_message_date__lt=datetime.fromtimestamp(offset_date, UTC))
    if folder_id is not None and issubclass(model, Dialog):
        query &= Q(folder_id=DialogFolderId(folder_id))
    if issubclass(model, Dialog):
        query &= Q(visible=True)

    dialogs: list[DialogT] = await model.filter(
        query
    ).limit(limit).order_by("-peer__last_message_date", "-peer__last_message_id", "-peer_id").select_related("peer")
    return await format_dialogs(model, tl_cls, tl_slice_cls, user_id, dialogs, allow_slicing, folder_id)


@handler.on_request(GetDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_dialogs(request: GetDialogs, user_id: int) -> Dialogs | DialogsSlice:
    return await get_dialogs_internal(
        Dialog, Dialogs, DialogsSlice, user_id, request.offset_id, request.offset_date, request.limit,
        request.offset_peer, request.folder_id, request.exclude_pinned, True,
    )


@handler.on_request(GetPeerDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_peer_dialogs(request: GetPeerDialogs, user_id: int) -> PeerDialogs:
    peer_user_ids = set()
    peer_chat_ids = set()
    peer_channel_ids = set()
    for peer_dialog in request.peers:
        if not isinstance(peer_dialog, InputDialogPeer):
            continue

        peer_info = Peer.type_and_id_from_input(user_id, peer_dialog.peer)
        if peer_info is None:
            continue

        peer_type, peer_target_id = peer_info
        if peer_type in (PeerType.SELF, PeerType.USER):
            peer_user_ids.add(peer_target_id)
        elif peer_type is PeerType.CHAT:
            peer_chat_ids.add(peer_target_id)
        elif peer_type is PeerType.CHANNEL:
            peer_channel_ids.add(peer_target_id)
        else:
            raise Unreachable

    if not peer_user_ids and not peer_chat_ids and not peer_channel_ids:
        return PeerDialogs(dialogs=[], messages=[], chats=[], users=[], state=await get_state_internal(user_id))

    peers_query = Q()
    if peer_user_ids:
        peers_query |= Q(peer__user_id__in=peer_user_ids)
    if peer_chat_ids:
        peers_query |= Q(peer__chat_id__in=peer_chat_ids)
    if peer_channel_ids:
        peers_query |= Q(peer__channel_id__in=peer_channel_ids)

    dialogs = await Dialog.filter(peers_query, owner_id=user_id).select_related("peer")
    dialogs_tl = await format_dialogs(Dialog, Dialogs, DialogsSlice, user_id, dialogs)

    return PeerDialogs(
        dialogs=dialogs_tl.dialogs,
        messages=dialogs_tl.messages,
        chats=dialogs_tl.chats,
        users=dialogs_tl.users,
        state=await get_state_internal(user_id),
    )


@handler.on_request(GetPinnedDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_pinned_dialogs(request: GetPinnedDialogs, user_id: int) -> PeerDialogs:
    dialogs = await Dialog.filter(
        owner_id=user_id, pinned_index__not_isnull=True, folder_id=DialogFolderId(request.folder_id), visible=True,
    ).select_related("peer").order_by("-pinned_index")

    dialogs_tl = await format_dialogs(Dialog, Dialogs, DialogsSlice, user_id, dialogs)
    return PeerDialogs(
        dialogs=dialogs_tl.dialogs,
        messages=dialogs_tl.messages,
        chats=dialogs_tl.chats,
        users=dialogs_tl.users,
        state=await get_state_internal(user_id),
    )


@handler.on_request(ToggleDialogPin, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_dialog_pin(request: ToggleDialogPin, user_id: int):
    if not isinstance(request.peer, InputDialogPeer):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    dialog = await Dialog.get_from_input_peer(
        user_id, request.peer.peer, "PEER_HISTORY_EMPTY"
    ).get_or_none().select_related("peer")
    if dialog is None:
        raise ErrorRpc(error_code=400, error_message="PEER_HISTORY_EMPTY")

    if (dialog.pinned_index is not None) == request.pinned:
        return True

    if request.pinned:
        max_index = cast(
            int | None,
            cast(
                object,
                await Dialog.filter(
                    owner=user_id, folder_id=dialog.folder_id, visible=True,
                ).annotate(max_pinned_index=Max("pinned_index")).first().values_list("max_pinned_index", flat=True)
            )
        )
        pinned_index = (max_index or -1) + 1
        if pinned_index > 10:
            raise ErrorRpc(error_code=400, error_message="PINNED_DIALOGS_TOO_MUCH")
        dialog.pinned_index = pinned_index
    else:
        dialog.pinned_index = None

    await dialog.save(update_fields=["pinned_index"])
    await upd.pin_dialog(user_id, dialog.peer, dialog)

    return True


@handler.on_request(ReorderPinnedDialogs, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def reorder_pinned_dialogs(request: ReorderPinnedDialogs, user_id: int):
    base_dialog_query = Dialog.filter(
        owner_id=user_id, folder_id=DialogFolderId(request.folder_id), visible=True,
    ).select_related("peer")

    pinned_now = {
        (dialog.peer.tup()): dialog
        for dialog in await base_dialog_query.filter(pinned_index__not_isnull=True)
    }
    pinned_after = []
    to_unpin: dict = pinned_now.copy() if request.force else {}

    dialogs_by_peers = pinned_now.copy()

    input_peers_to_fetch = []

    for dialog_peer in request.order:
        if not isinstance(dialog_peer, InputDialogPeer):
            continue

        peer_info = Peer.type_and_id_from_input(user_id, dialog_peer.peer)
        if peer_info is None or peer_info in dialogs_by_peers:
            continue

        input_peers_to_fetch.append(dialog_peer.peer)

    for dialog in await Dialog.get_from_input_peer_many(user_id, input_peers_to_fetch).select_related("peer"):
        dialogs_by_peers[(dialog.peer.tup())] = dialog

    for dialog_peer in request.order:
        if not isinstance(dialog_peer, InputDialogPeer):
            continue

        peer_info = Peer.type_and_id_from_input(user_id, dialog_peer.peer)
        if peer_info is None:
            continue

        dialog = dialogs_by_peers.get(peer_info, None)
        if not dialog:
            continue

        pinned_after.append(dialog)
        to_unpin.pop(peer_info, None)

    if not request.force:
        pinned_after.extend(sorted(pinned_now.values(), key=lambda d: d.pinned_index or 0))

    if to_unpin:
        unpin_ids = [dialog.id for dialog in to_unpin.values()]
        await Dialog.filter(id__in=unpin_ids).update(pinned_index=None)

    for idx, dialog in enumerate(reversed(pinned_after)):
        dialog.pinned_index = idx

    if pinned_after:
        await Dialog.bulk_update(pinned_after, fields=["pinned_index"])
    await upd.reorder_pinned_dialogs(user_id, pinned_after)

    return True


@handler.on_request(MarkDialogUnread, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def mark_dialog_unread(request: MarkDialogUnread, user_id: int) -> bool:
    if not isinstance(request.peer, InputDialogPeer):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    dialog = await Dialog.get_from_input_peer(user_id, request.peer.peer).get_or_none().select_related("peer")
    if dialog is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    if dialog.unread_mark == request.unread:
        return True

    dialog.unread_mark = request.unread
    await dialog.save(update_fields=["unread_mark"])
    await upd.update_dialog_unread_mark(user_id, dialog)

    return True


@handler.on_request(GetDialogUnreadMarks, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_dialog_unread_marks(user_id: int) -> TLObjectVector[TLDialogPeerBase]:
    peers = await Peer.filter(dialogs__owner_id=user_id, dialogs__unread_mark=True, dialogs__visible=True)

    return TLObjectVector([
        DialogPeer(peer=peer.to_tl())
        for peer in peers
    ])


@handler.on_request(EditPeerFolders, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def edit_peer_folders(request: EditPeerFolders, user_id: int) -> Updates:
    for folder_peer in request.folder_peers:
        if folder_peer.folder_id not in DialogFolderId._value2member_map_:
            raise ErrorRpc(error_code=400, error_message="FOLDER_ID_INVALID")

    dialogs = {
        dialog.peer.tup(): dialog
        for dialog in await Dialog.get_from_input_peer_many(
            user_id, [folder_peer.peer for folder_peer in request.folder_peers],
        ).select_related("peer")
    }

    updated_dialogs = []

    for folder_peer in request.folder_peers:
        peer_info = Peer.type_and_id_from_input(user_id, folder_peer.peer)
        if peer_info is None or peer_info not in dialogs:
            continue

        dialog = dialogs[peer_info]
        new_folder_id = DialogFolderId(folder_peer.folder_id)
        if dialog.folder_id == new_folder_id:
            continue

        dialog.folder_id = new_folder_id
        updated_dialogs.append(dialog)

    await Dialog.bulk_update(updated_dialogs, ["folder_id"])
    return await upd.update_folder_peers(user_id, updated_dialogs)
