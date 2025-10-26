from datetime import datetime, UTC
from time import time
from typing import cast, Any

from loguru import logger
from pypika_tortoise import SqlContext, Dialects
from pypika_tortoise.terms import Function as PypikaFunction
from pypika_tortoise.utils import format_alias_sql
from tortoise import connections
from tortoise.expressions import Q, Subquery, Function, CombinedExpression, Connector
from tortoise.functions import Min, Max, Count
from tortoise.queryset import QuerySet

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.utils import USERNAME_REGEX_NO_LEN
from piltover.db.enums import MediaType, PeerType, FileType, MessageType, ChatAdminRights
from piltover.db.models import User, MessageDraft, ReadState, State, Peer, ChannelPostInfo, Message, MessageMention, \
    ChatParticipant, Chat
from piltover.db.models._utils import resolve_users_chats
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import Updates, InputPeerUser, InputPeerSelf, UpdateDraftMessage, InputMessagesFilterEmpty, TLObject, \
    InputMessagesFilterPinned, User as TLUser, InputMessageID, InputMessageReplyTo, InputMessagesFilterDocument, \
    InputMessagesFilterPhotos, InputMessagesFilterPhotoVideo, InputMessagesFilterVideo, \
    InputMessagesFilterGif, InputMessagesFilterVoice, InputMessagesFilterMusic, MessageViews, \
    InputMessagesFilterMyMentions, SearchResultsCalendarPeriod, TLObjectVector, MessageActionSetMessagesTTL
from piltover.tl.functions.messages import GetHistory, ReadHistory, GetSearchCounters, Search, GetAllDrafts, \
    SearchGlobal, GetMessages, GetMessagesViews, GetSearchResultsCalendar, GetOutboxReadDate, GetMessages_57, \
    GetUnreadMentions_133, GetUnreadMentions, ReadMentions, ReadMentions_133, GetSearchResultsCalendar_134, \
    ReadMessageContents, SetHistoryTTL
from piltover.tl.types.messages import Messages, AffectedMessages, SearchCounter, MessagesSlice, \
    MessageViews as MessagesMessageViews, SearchResultsCalendar, AffectedHistory
from piltover.worker import MessageHandler

handler = MessageHandler("messages.history")


def message_filter_to_query(filter_: TLObject | None) -> Q | None:
    if isinstance(filter_, InputMessagesFilterPinned):
        return Q(pinned=True)
    elif isinstance(filter_, InputMessagesFilterDocument):
        return Q(media__type=MediaType.DOCUMENT)
    elif isinstance(filter_, InputMessagesFilterPhotos):
        return Q(media__type=MediaType.PHOTO)
    elif isinstance(filter_, InputMessagesFilterPhotoVideo):
        return Q(media__type=MediaType.PHOTO) | Q(media__file__type=FileType.DOCUMENT_VIDEO)
    elif isinstance(filter_, InputMessagesFilterVideo):
        return Q(media__file__type=FileType.DOCUMENT_VIDEO)
    elif isinstance(filter_, InputMessagesFilterGif):
        return Q(media__file__type=FileType.DOCUMENT_GIF)
    elif isinstance(filter_, InputMessagesFilterVoice):
        return Q(media__file__type=FileType.DOCUMENT_VOICE) | Q(media__file__type=FileType.DOCUMENT_VIDEO_NOTE)
    elif isinstance(filter_, InputMessagesFilterMusic):
        return Q(media__file__type=FileType.DOCUMENT_AUDIO)
    elif filter_ is not None and not isinstance(filter_, InputMessagesFilterEmpty):
        # TODO: InputMessagesFilterUrl
        logger.warning(f"Unsupported filter: {filter_}")
        return Q(id=0)

    return None


# `peer` is Peer if fetching messages between current user (peer.owner) and peer
# `peer` is User if fetching messages globally (such as global search)
async def get_messages_query_internal(
        peer: Peer | User, max_id: int, min_id: int, offset_id: int, limit: int, add_offset: int,
        from_user_id: int | None = None, min_date: int | None = None, max_date: int | None = None, q: str | None = None,
        filter_: TLObject | None = None, saved_peer: Peer | None = None, after_reaction_id: int | None = None,
        only_mentions: bool = False,
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

    if filter_ is not None and (filter_query := message_filter_to_query(filter_)) is not None:
        query &= filter_query

    if after_reaction_id is not None:
        user_id = peer.owner_id if isinstance(peer, Peer) else peer.id
        query &= Q(messagereactions__id__gt=after_reaction_id, author__id__not=user_id)

    if only_mentions:
        read_state = await ReadState.for_peer(peer=peer)
        query &= Q(id__in=Subquery(
            MessageMention.filter(peer=peer, id__gt=read_state.last_mention_id).values_list("message__id", flat=True)
        ))

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
    message_ids_after_offset = await Message.filter(
        query & Q(id__gte=offset_id)
    ).limit(after_offset_limit).order_by("date").values_list("id", flat=True)

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
        filter_: TLObject | None = None, saved_peer: Peer | None = None, after_reaction_id: int | None = None,
) -> list[Message]:
    query = await get_messages_query_internal(
        peer, max_id, min_id, offset_id, limit, add_offset, from_user_id, min_date, max_date, q, filter_, saved_peer,
        after_reaction_id,
    )
    return await query


async def format_messages_internal(
        user: User, messages: list[Message], add_users: dict[int, TLUser] | None = None, allow_slicing: bool = False,
        peer: Peer | None = None, saved_peer: Peer | None = None, offset_id: int | None = None,
        query: QuerySet[Message] | None = None, with_reactions: bool = False,
) -> Messages | MessagesSlice:
    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    messages_tl = []
    for message in messages:
        messages_tl.append(await message.to_tl(user, with_reactions))
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

    if add_users:
        users_q &= Q(id__not_in=list(add_users.keys()))

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

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

    chats_tl = [*chats.values(), *channels.values()]
    users_tl = list(users.values())

    if not allow_slicing or not peer:
        return Messages(
            messages=messages_tl,
            chats=chats_tl,
            users=users_tl,
        )

    if query is None:
        query = Q(peer=peer)
        if saved_peer is not None:
            query &= Q(fwd_header__saved_peer=saved_peer)
    messages_count = await Message.filter(query).count()

    if messages_count <= len(messages_tl) and not offset_id:
        return Messages(
            messages=messages_tl,
            chats=chats_tl,
            users=users_tl,
        )

    if offset_id:
        offset_id_offset = await Message.filter(query & Q(id__gte=offset_id)).count()
    else:
        offset_id_offset = 0

    return MessagesSlice(
        inexact=False,
        count=messages_count,
        next_rate=None,
        offset_id_offset=offset_id_offset,
        messages=messages_tl,
        chats=chats_tl,
        users=users_tl,
    )


@handler.on_request(GetHistory)
async def get_history(request: GetHistory, user: User) -> Messages:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    messages = await get_messages_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset
    )
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    return await format_messages_internal(user, messages, allow_slicing=True, peer=peer, offset_id=request.offset_id)


@handler.on_request(GetMessages)
async def get_messages(request: GetMessages, user: User) -> Messages:
    query = Q()

    for message_query in request.id:
        if isinstance(message_query, InputMessageID):
            query |= Q(id=message_query.id)
        elif isinstance(message_query, InputMessageReplyTo):
            query |= Q(id=Subquery(
                Message.filter(
                    peer__owner=user, id=message_query.id
                ).first().values_list("reply_to__id", flat=True)
            ))

    query &= Q(peer__owner=user)

    return await format_messages_internal(user, await Message.filter(query).select_related("peer"))


@handler.on_request(GetMessages_57)
async def get_messages_57(request: GetMessages_57, user: User) -> Messages:
    return await format_messages_internal(
        user,
        await Message.filter(id__in=request.id[:100], peer__owner=user).select_related("peer"),
    )


@handler.on_request(ReadHistory)
async def read_history(request: ReadHistory, user: User):
    peer = await Peer.from_input_peer_raise(user, request.peer)

    state, _ = await State.get_or_create(user=user)

    read_state, created = await ReadState.get_or_create(peer=peer)
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

    logger.info(f"Set last read message id to {message_id} for peer {peer.id} of user {user.id}")

    messages_out: dict[Peer, tuple[int, int]] = {}
    for other in await peer.get_opposite():
        count = await Message.filter(id__gt=old_last_message_id, internal_id__lte=internal_id, peer=other).count()
        if not count:
            continue
        last_id = await Message.filter(peer=other, internal_id__lte=internal_id).first().values_list("id", flat=True)
        messages_out[other] = (cast(int, last_id), count)

    await upd.update_read_history_inbox(peer, message_id, messages_count, unread_count)
    await upd.update_read_history_outbox(messages_out)

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

    return TLObjectVector([
        SearchCounter(
            filter=filt,
            count=await (await get_messages_query_internal(
                peer, 0, 0, 0, 0, 0, 0, 0, 0, None, filt, saved_peer,
            )).count(),
        ) for filt in request.filters
    ])


@handler.on_request(GetAllDrafts)
async def get_all_drafts(user: User):
    users_q = Q()
    chats_q = Q()
    channels_q = Q()

    updates = []
    drafts = await MessageDraft.filter(dialog__peer__owner=user).select_related(
        "dialog", "dialog__peer", "dialog__peer__user",
    )
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


@handler.on_request(GetMessagesViews)
async def get_messages_views(request: GetMessagesViews, user: User) -> MessagesMessageViews:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    request.id = request.id[:100]

    query = Q(id__in=request.id)
    query &= Q(peer__owner=None, peer__channel=peer.channel) if peer.type is PeerType.CHANNEL else Q(peer=peer)

    message: Message
    messages = {
        message.id: message
        async for message in Message.filter(query).select_related("post_info", "peer", "peer__channel")
    }

    channels = {}
    views = []
    incremented = []

    for message_id in request.id:
        if message_id not in messages or not messages[message_id].post_info:
            views.append(MessageViews())
            continue

        message = messages[message_id]
        # TODO: count unique views
        if request.increment:
            message.post_info.views += 1
            incremented.append(message.post_info)

        views.append(MessageViews(views=message.post_info.views))

        # TODO: load channel from fwd_header
        if message.peer.channel_id is not None:
            channels[message.peer.channel.id] = await message.peer.channel.to_tl(user)

    if incremented:
        await ChannelPostInfo.bulk_update(incremented, fields=["views"])

    return MessagesMessageViews(
        views=views,
        chats=list(channels.values()),
        users=[],
    )


class DatetimeToUnixPika(PypikaFunction):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(kwargs.get("alias"))
        self.args: list = [self.wrap_constant(param) for param in args]

    def get_function_sql(self, ctx: SqlContext) -> str:
        args = ",".join(self.get_arg_sql(arg, ctx) for arg in self.args)

        if ctx.dialect is Dialects.MYSQL:
            return f"UNIX_TIMESTAMP({args})"
        elif ctx.dialect is Dialects.SQLITE:
            return f"CAST(strftime('%s', {args}) AS INT)"
        elif ctx.dialect is Dialects.POSTGRESQL:
            return f"DATE_PART('epoch', {args})"
        elif ctx.dialect is Dialects.MSSQL:
            return f"DATEDIFF(SECOND, '1970-01-01', {args})"

        raise RuntimeError(f"Dialect {ctx.dialect!r} is not supported!")

    def get_sql(self, ctx: SqlContext) -> str:
        function_sql = self.get_function_sql(ctx)

        if ctx.with_alias:
            return format_alias_sql(function_sql, self.alias, ctx)

        return function_sql


class DatetimeToUnix(Function):
    database_func = DatetimeToUnixPika

    @staticmethod
    def is_supported(dialect: str) -> bool:
        return dialect in ("mysql", "sqlite", "postgres", "postgresql", "mssql")


@handler.on_request(GetSearchResultsCalendar_134)
@handler.on_request(GetSearchResultsCalendar)
async def get_search_results_calendar(request: GetSearchResultsCalendar, user: User) -> SearchResultsCalendar:
    if isinstance(request.filter, (InputMessagesFilterEmpty, InputMessagesFilterMyMentions)):
        raise ErrorRpc(error_code=400, error_message="FILTER_NOT_SUPPORTED")

    peer = await Peer.from_input_peer_raise(user, request.peer)
    saved_peer = None
    if peer.type is PeerType.SELF and not isinstance(request, GetSearchResultsCalendar_134) and request.saved_peer_id:
        saved_peer = await Peer.from_input_peer_raise(user, request.saved_peer_id)

    if (filter_query := message_filter_to_query(request.filter)) is None:
        raise ErrorRpc(error_code=400, error_message="FILTER_NOT_SUPPORTED")

    query = Q(peer=peer) & filter_query
    if saved_peer is not None:
        query &= Q(fwd_header__saved_peer=saved_peer)

    dialect = connections.get("default").capabilities.dialect
    if not DatetimeToUnix.is_supported(dialect):
        logger.warning(f"Dialect \"{dialect}\" is not supported in GetSearchResultsCalendar")
        periods = []
    else:
        query = Message.annotate(
            day=CombinedExpression(DatetimeToUnix("date"), Connector.div, 86400),
            min_msg_id=Min("id"), max_msg_id=Max("id"), msg_count=Count("id")
        ).filter(
            query & Q(msg_count__gte=1)
        ).limit(100).order_by("-day").group_by("day").values_list("day", "min_msg_id", "max_msg_id", "msg_count")
        logger.trace(query.sql())
        periods = await query

    message_ids = []
    periods_tl = []

    for day, min_msg_id, max_msg_id, msg_count in periods:
        message_ids.append(min_msg_id)
        if max_msg_id != min_msg_id:
            message_ids.append(max_msg_id)

        periods_tl.append(SearchResultsCalendarPeriod(
            date=day * 86400,
            min_msg_id=min_msg_id,
            max_msg_id=max_msg_id,
            count=msg_count,
        ))

    messages = await Message.filter(id__in=message_ids)
    messages_tl = []
    users_q, chats_q, channels_q = Q(), Q(), Q()

    for message in messages:
        messages_tl.append(await message.to_tl(user))
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    return SearchResultsCalendar(
        count=0,  # TODO: add count by request.filter
        min_date=periods[-1][0] if periods else 0,
        min_msg_id=periods[-1][1] if periods else 0,
        offset_id_offset=None,  # TODO: add offset_id support
        periods=periods_tl,
        messages=messages_tl,
        chats=[*chats.values(), *channels.values()],
        users=list(users.values()),
    )


@handler.on_request(GetOutboxReadDate)
async def get_outbox_read_date():
    # TODO: implement getting outbox read date

    raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")


@handler.on_request(GetUnreadMentions_133)
@handler.on_request(GetUnreadMentions)
async def get_unread_mentions(request: GetUnreadMentions, user: User) -> Messages | MessagesSlice:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    query = await get_messages_query_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, only_mentions=True
    )
    messages = await query

    return await format_messages_internal(user, messages, peer=peer, query=query, offset_id=request.offset_id)


@handler.on_request(ReadMentions_133)
@handler.on_request(ReadMentions)
async def read_mentions(request: ReadMentions, user: User) -> AffectedHistory:
    peer = await Peer.from_input_peer_raise(user, request.peer)

    read_state = await ReadState.for_peer(peer=peer)
    mention_ids = await MessageMention.filter(
        peer=peer, id__gt=read_state.last_mention_id,
    ).values_list("id", flat=True)
    logger.trace(f"Unread mentions ids: {mention_ids}")

    pts_count = len(mention_ids)

    if not mention_ids:
        return AffectedHistory(
            pts=await State.add_pts(user, 0),
            pts_count=0,
            offset=0,
        )

    await ReadState.filter(id=read_state.id).update(last_mention_id=max(mention_ids))

    # TODO: check if in channels, other updates are emitted
    #  (because UpdateReadMessagesContents is for common (user-specific) message box only)
    if peer.type is not PeerType.CHANNEL:
        pts, _ = await upd.read_messages_contents(user, mention_ids)
    else:
        pts = await State.add_pts(user, pts_count)

    return AffectedHistory(
        pts=pts,
        pts_count=pts_count,
        offset=0,
    )


@handler.on_request(ReadMessageContents)
async def read_message_contents(request: ReadMessageContents, user: User) -> AffectedMessages:
    if not request.id:
        return AffectedMessages(
            pts=await State.add_pts(user, 0),
            pts_count=0,
        )

    mentions = await MessageMention.filter(
        peer__owner=user, peer__type__not=PeerType.CHANNEL, message__id__in=request.id[:100],
    ).select_related("peer")

    if not mentions:
        return AffectedMessages(
            pts=await State.add_pts(user, 0),
            pts_count=0,
        )

    max_mention_id_by_peer = {}
    message_ids = set()

    for mention in mentions:
        message_ids.add(mention.message_id)
        peer = mention.peer
        if peer not in max_mention_id_by_peer or mention.id > max_mention_id_by_peer[peer]:
            max_mention_id_by_peer[peer] = mention.id

    to_update = []
    for peer, max_mention_id in max_mention_id_by_peer.items():
        read_state = await ReadState.for_peer(peer=peer)
        if max_mention_id > read_state.last_mention_id:
            read_state.last_mention_id = max_mention_id
            to_update.append(read_state)

    if to_update:
        await ReadState.bulk_update(to_update, fields=["last_mention_id"])

    message_ids = list(message_ids)
    pts, _ = await upd.read_messages_contents(user, message_ids)

    return AffectedMessages(
        pts=pts,
        pts_count=len(message_ids),
    )


@handler.on_request(SetHistoryTTL)
async def set_history_ttl(request: SetHistoryTTL, user: User) -> Updates:
    if request.period % 86400 != 0:
        raise ErrorRpc(error_code=400, error_message="TTL_PERIOD_INVALID")

    ttl_days = request.period // 86400
    peer = await Peer.from_input_peer_raise(user, request.peer)

    if peer.type is PeerType.SELF:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    elif peer.type is PeerType.USER:
        if peer.user_ttl_period_days == ttl_days:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
        opp_peer, _ = await Peer.get_or_create(type=PeerType.USER, owner=peer.user, user=peer.owner)
        peer.user_ttl_period_days = opp_peer.user_ttl_period_days = ttl_days
        await Peer.bulk_update([peer, opp_peer], fields=["user_ttl_period_days"])
    elif peer.type in (PeerType.CHAT, PeerType.CHANNEL):
        participant = await ChatParticipant.get_or_none(**Chat.or_channel(peer.chat_or_channel), user=user)
        if peer.type is PeerType.CHAT \
                and (participant is None or not (participant.is_admin or peer.chat.creator_id == user.id)):
            raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")
        elif peer.type is PeerType.CHANNEL \
                and not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
            raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

        await peer.chat_or_channel.update(ttl_period_days=ttl_days)
    else:
        raise Unreachable

    if peer.type is PeerType.CHANNEL:
        updates = await upd.update_channel(peer.channel, user)
    else:
        updates = await upd.update_history_ttl(peer, ttl_days)

    updates_msg = await send_message_internal(
        user, peer, None, None, False,
        author=user, type=MessageType.SERVICE_CHAT_UPDATE_TTL, ttl_period_days=None,
        extra_info=MessageActionSetMessagesTTL(period=ttl_days * 86400).write(),
    )
    updates.updates.extend(updates_msg.updates)
    updates.users.extend(updates_msg.users)
    updates.chats.extend(updates_msg.chats)

    return updates
