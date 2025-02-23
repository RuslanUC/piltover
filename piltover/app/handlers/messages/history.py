from datetime import datetime, UTC
from time import time
from typing import cast

from loguru import logger
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.app.utils.utils import USERNAME_REGEX_NO_LEN
from piltover.db.enums import MediaType, PeerType, FileType, MessageType
from piltover.db.models import User, MessageDraft, ReadState, State, Peer, Dialog
from piltover.db.models._utils import resolve_users_chats
from piltover.db.models.message import Message
from piltover.tl import Updates, InputPeerUser, InputPeerSelf, UpdateDraftMessage, InputMessagesFilterEmpty, TLObject, \
    InputMessagesFilterPinned, User as TLUser, InputMessageID, InputMessageReplyTo, InputMessagesFilterDocument, \
    InputMessagesFilterPhotos, InputMessagesFilterPhotoVideo, Chat as TLChat, InputMessagesFilterVideo, \
    InputMessagesFilterGif, InputMessagesFilterVoice, InputMessagesFilterMusic
from piltover.tl.functions.messages import GetHistory, ReadHistory, GetSearchCounters, Search, GetAllDrafts, \
    SearchGlobal, GetMessages
from piltover.tl.types.messages import Messages, AffectedMessages, SearchCounter
from piltover.worker import MessageHandler

handler = MessageHandler("messages.history")


async def _get_messages_query(
        peer: Peer | User, max_id: int, min_id: int, offset_id: int, limit: int, add_offset: int,
        from_user_id: int | None = None, min_date: int | None = None, max_date: int | None = None, q: str | None = None,
        filter_: TLObject | None = None, saved_peer: Peer | None = None,
) -> QuerySet[Message]:
    query = Q(peer=peer) if isinstance(peer, Peer) else Q(peer__owner=peer)
    if isinstance(peer, Peer) and peer.type is PeerType.CHANNEL:
        query |= Q(peer__owner=None, peer__channel__id=peer.channel_id)

    # TODO: probably dont add this to query if user requested messages with InputMessageReplyTo or something
    # TODO: why did i even add this in the first place???
    query &= Q(type=MessageType.REGULAR)

    if q:
        query &= Q(message__istartswith=q)

    if from_user_id:
        query &= Q(author__id=from_user_id)

    if min_date:
        query &= Q(date__gt=datetime.fromtimestamp(min_date, UTC))
    if max_date:
        query &= Q(date__lt=datetime.fromtimestamp(max_date, UTC))

    if max_id:
        query &= Q(id__lt=max_id)
    if min_id:
        query &= Q(id__gt=min_id)

    if isinstance(peer, Peer) and peer.type is PeerType.SELF and saved_peer is not None:
        query &= Q(fwd_header__saved_peer=saved_peer)

    if isinstance(filter_, InputMessagesFilterPinned):
        query &= Q(pinned=True)
    elif isinstance(filter_, InputMessagesFilterDocument):
        query &= Q(media__type=MediaType.DOCUMENT)
    elif isinstance(filter_, InputMessagesFilterPhotos):
        query &= Q(media__type=MediaType.PHOTO)
    elif isinstance(filter_, InputMessagesFilterPhotoVideo):
        query &= (Q(media__type=MediaType.PHOTO) | Q(media__file__type=FileType.DOCUMENT_VIDEO))
    elif isinstance(filter_, InputMessagesFilterVideo):
        query &= Q(media__file__type=FileType.DOCUMENT_VIDEO)
    elif isinstance(filter_, InputMessagesFilterGif):
        query &= Q(media__file__type=FileType.DOCUMENT_GIF)
    elif isinstance(filter_, InputMessagesFilterVoice):
        query &= (Q(media__file__type=FileType.DOCUMENT_VOICE) | Q(media__file__type=FileType.DOCUMENT_VIDEO_NOTE))
    elif isinstance(filter_, InputMessagesFilterMusic):
        query &= Q(media__file__type=FileType.DOCUMENT_AUDIO)
    elif filter_ is not None and not isinstance(filter_, InputMessagesFilterEmpty):
        # TODO: InputMessagesFilterUrl
        logger.warning(f"Unsupported filter: {filter_}")
        query = Q(id=0)

    limit = max(min(100, limit), 1)
    select_related = "author", "peer", "peer__user"

    if not offset_id or add_offset >= 0:
        if offset_id:
            query &= Q(id__lt=offset_id)

        return Message.filter(query).limit(limit).offset(add_offset).order_by("-date").select_related(*select_related)

    """
    (based in https://core.telegram.org/api/offsets)
    Some things like negative offsets, etc. confusing me a little bit, so here's how i understood them: 
    
    Messages with following ids are in database:
    1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30
    
    Client has messages 15-30, makes request: GetHistory(offset_id=15, limit=15),
      then we need to fetch following messages (from newest to oldest, right to left here):
    1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30
    ^------------------------------^
    (to here)            (from here)
    
    If client makes request like GetHistory(offset_id=25, limit=10),
      then we need to fetch like this:
    1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30
                                     ^---------------------------^
                                     (to here)         (from here)
                      
    If client makes request like GetHistory(offset_id=25, limit=10, add_offset=5),
      then we need to fetch like this (since we are ordering by date DESC, we just add add_offset as sql offset):
    1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30
                      ^---------------------------^
                      (to here)         (from here)
                      
    If client makes request like GetHistory(offset_id=25, limit=10, add_offset=-5),
      then we need to fetch like this (we need to fetch 5 (limit - abs(add_offset)?) messages before offset_id 
      and 5 messages after (and including) offset_id):
    1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30
                                                    ^---------------------------^
                                                    (to here)         (from here)
    Since sql can't do negative offsets, we need to fetch -add_offset messages after (and including) 
      offset_id (ordering by date ASC), then fetch (limit - (-[number of messages fetched in first query])) 
      message before offset_id (date DESC)
    """

    after_offset_limit = min(abs(add_offset), limit)
    message_ids_after_offset = await Message.filter(query & Q(id__gte=offset_id)).limit(after_offset_limit).order_by("date").values_list("id", flat=True)

    if len(message_ids_after_offset) >= limit:
        return Message.filter(id__in=message_ids_after_offset).order_by("-date").select_related(*select_related)

    limit -= len(message_ids_after_offset)

    query &= Q(id__lt=offset_id)
    message_ids_before_offset = await Message.filter(query).limit(limit).order_by("-date").values_list("id", flat=True)

    final_query = Q(id__in=message_ids_before_offset) | Q(id__in=message_ids_after_offset)
    return Message.filter(final_query).order_by("-date").select_related(*select_related)

async def get_messages_internal(
        peer: Peer | User, max_id: int, min_id: int, offset_id: int, limit: int, add_offset: int,
        from_user_id: int | None = None, min_date: int | None = None, max_date: int | None = None, q: str | None = None,
        filter_: TLObject | None = None, saved_peer: Peer | None = None,
) -> list[Message]:
    query = await _get_messages_query(
        peer, max_id, min_id, offset_id, limit, add_offset, from_user_id, min_date, max_date, q, filter_, saved_peer,
    )
    return await query


async def format_messages_internal(
        user: User, messages: list[Message], add_users: dict[int, TLUser] | None = None,
) -> Messages:
    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    messages_tl = []
    for message in messages:
        messages_tl.append(await message.to_tl(user))
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

    if add_users:
        users_q &= Q(id__not_in=list(add_users.keys()))

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    # TODO: MessagesSlice based on explanation below
    """
    Messages with following ids are in database:
    1 .. 90
    
    If client makes request GetHistory(limit=100),
      we just return Messages object with all 90 messages.
    
    If client makes request GetHistory(limit=50),
      we return MessagesSlice object with last (order by -id) 50 messages: 40-89.
      
    If client makes request like GetHistory(limit=50, offset_id=80),
      we return MessagesSlice object with messages 20-79 and offset_id_offset=10.
    
    If client makes request like GetHistory(limit=50, offset_id=80, add_offset=10),
      we return MessagesSlice object with messages 20-69 and offset_id_offset=10.
    
    If client makes request like GetHistory(limit=50, max_id=80),
      we return MessagesSlice object with messages 30-79 and offset_id_offset=None.
    
    If client makes request like GetHistory(limit=50, offset_id=80, max_id=75),
      we return MessagesSlice object with messages 25-74 and offset_id_offset=10.
    
    In all MessagesSlice responses: inexact=False, count=90.
    
    NOTE TO MYSELF: all values are tested with only GetHistory request. Search, GetReplies, etc. were NOT tested.
    """

    return Messages(
        messages=messages_tl,
        chats=[*chats.values(), *channels.values()],
        users=list(users.values()),
    )


@handler.on_request(GetHistory)
async def get_history(request: GetHistory, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    messages = await get_messages_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset
    )
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    return await format_messages_internal(user, messages)


@handler.on_request(GetMessages)
async def get_messages(request: GetMessages, user: User) -> Messages:
    query = Q()

    for message_query in request.id:
        if isinstance(message_query, InputMessageID):
            query |= Q(id=message_query.id)
        elif isinstance(message_query, InputMessageReplyTo):
            query |= Q(reply_to__id=message_query.id)
        # TODO: InputMessagePinned ?

    query &= Q(peer__owner=user)

    return await format_messages_internal(user, await Message.filter(query))


@handler.on_request(ReadHistory)
async def read_history(request: ReadHistory, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    state, _ = await State.get_or_create(user=user)

    if (dialog := await Dialog.get_or_none(peer=peer)) is None:
        return AffectedMessages(
            pts=state.pts,
            pts_count=0,
        )

    read_state, created = await ReadState.get_or_create(dialog=dialog, defaults={"last_message_id": 0})
    if request.max_id <= read_state.last_message_id:
        return AffectedMessages(
            pts=state.pts,
            pts_count=0,
        )

    message_id, internal_id = await Message.filter(
        id__lte=request.max_id, peer=peer,
    ).order_by("-id").first().values_list("id", "internal_id")
    if not message_id:
        return AffectedMessages(
            pts=state.pts,
            pts_count=0,
        )

    old_last_message_id = read_state.last_message_id
    messages_count = await Message.filter(id__gt=old_last_message_id, id__lte=message_id, peer=peer).count()
    unread_count = await Message.filter(peer=peer, id__gt=message_id).count()

    read_state.last_message_id = message_id
    await read_state.save(update_fields=["last_message_id"])
    state.pts += messages_count
    await state.save(update_fields=["pts"])

    messages_out: dict[Peer, tuple[int, int]] = {}
    for other in await peer.get_opposite():
        count = await Message.filter(id__gt=old_last_message_id, internal_id__lte=internal_id, peer=other).count()
        if not count:
            continue
        last_id = await Message.filter(peer=other, internal_id__lte=internal_id).first().values_list("id", flat=True)
        messages_out[other] = (cast(int, last_id), count)

    await UpdatesManager.update_read_history_inbox(peer, message_id, messages_count, unread_count)
    await UpdatesManager.update_read_history_outbox(messages_out)

    return AffectedMessages(
        pts=state.pts,
        pts_count=messages_count,
    )


@handler.on_request(Search)
async def messages_search(request: Search, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    saved_peer = None
    if peer.type is PeerType.SELF and request.saved_peer_id:
        saved_peer = await Peer.from_input_peer_raise(user, request.saved_peer_id)

    from_user_id = None
    if isinstance(request.from_id, InputPeerUser):
        from_user_id = request.from_id.user_id
    elif isinstance(request.from_id, InputPeerSelf):
        from_user_id = user.id

    messages = await get_messages_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, from_user_id,
        request.min_date, request.max_date, request.q, request.filter, saved_peer,
    )

    return await format_messages_internal(user, messages)


@handler.on_request(GetSearchCounters)
async def get_search_counters(request: GetSearchCounters, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)
    saved_peer = None
    if peer.type is PeerType.SELF and request.saved_peer_id:
        saved_peer = await Peer.from_input_peer_raise(user, request.saved_peer_id)

    return [
        SearchCounter(
            filter=filt,
            count=await (await _get_messages_query(peer, 0, 0, 0, 0, 0, 0, 0, 0, None, filt, saved_peer)).count(),
        ) for filt in request.filters
    ]


@handler.on_request(GetAllDrafts)
async def get_all_drafts(user: User):
    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    updates = []
    drafts = await MessageDraft.filter(dialog__peer__owner=user).select_related("dialog", "dialog__peer", "dialog__peer__user")
    for draft in drafts:
        peer = draft.dialog.peer
        updates.append(UpdateDraftMessage(peer=peer.to_tl(), draft=draft.to_tl()))
        users_q, chats_q, channels_q = peer.query_users_chats(users_q, chats_q, channels_q)

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    return Updates(
        updates=updates,
        users=list(users.values()),
        chats=[*chats.values(), *channels.values()],
        date=int(time()),
        seq=0,
    )


@handler.on_request(SearchGlobal)
async def search_global(request: SearchGlobal, user: User):
    users = {}

    q = user_q = request.q
    if q.startswith("@"):
        user_q = q[1:]
    if USERNAME_REGEX_NO_LEN.match(user_q):
        users = {
            oth_user.id: await oth_user.to_tl(user)
            for oth_user in await User.filter(username__istartswith=user_q).limit(10)
        }

    limit = max(min(request.limit, 1), 10)

    # TODO: offset_peer ?
    messages = await get_messages_internal(
        user, 0, 0, request.offset_id, limit, 0, 0,
        request.min_date, request.max_date, request.q, request.filter
    )

    return await format_messages_internal(user, messages, users)
