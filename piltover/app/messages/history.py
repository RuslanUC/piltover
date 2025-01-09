from datetime import datetime, UTC
from time import time

from loguru import logger
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.app.account import username_regex_no_len
from piltover.db.enums import MessageType, MediaType, PeerType, FileType
from piltover.db.models import User, MessageDraft, ReadState, State, Peer
from piltover.db.models.message import Message
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl import Updates, InputPeerUser, InputPeerSelf, UpdateDraftMessage, InputMessagesFilterEmpty, TLObject, \
    InputMessagesFilterPinned, User as TLUser, InputMessageID, InputMessageReplyTo, InputMessagesFilterDocument, \
    InputMessagesFilterPhotos, InputMessagesFilterPhotoVideo, Chat as TLChat, InputMessagesFilterVideo, \
    InputMessagesFilterGif, InputMessagesFilterVoice, InputMessagesFilterMusic
from piltover.tl.functions.messages import GetHistory, ReadHistory, GetSearchCounters, Search, GetAllDrafts, \
    SearchGlobal, GetMessages
from piltover.tl.types.messages import Messages, AffectedMessages, SearchCounter

handler = MessageHandler("messages.history")


def _get_messages_query(
        peer: Peer | User, max_id: int, min_id: int, offset_id: int, limit: int, add_offset: int,
        from_user_id: int | None = None, min_date: int | None = None, max_date: int | None = None, q: str | None = None,
        filter_: TLObject | None = None
) -> QuerySet[Message]:
    query = Q(peer=peer) if isinstance(peer, Peer) else Q(peer__owner=peer)
    # TODO: probably dont add this to query if user requested messages with InputMessageReplyTo or something
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
        query &= Q(id__lte=max_id)
    if min_id:
        query &= Q(id__gte=min_id)

    if offset_id:
        query &= Q(id__lt=offset_id)

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
    return Message.filter(query).limit(limit).offset(add_offset).order_by("-date")\
        .select_related("author", "peer", "peer__user")

async def get_messages_internal(
        peer: Peer | User, max_id: int, min_id: int, offset_id: int, limit: int, add_offset: int,
        from_user_id: int | None = None, min_date: int | None = None, max_date: int | None = None, q: str | None = None,
        filter_: TLObject | None = None
) -> list[Message]:
    return await _get_messages_query(
        peer, max_id, min_id, offset_id, limit, add_offset, from_user_id, min_date, max_date, q, filter_,
    )


async def _format_messages(
        user: User, messages: list[Message], users: dict[int, TLUser] | None = None,
        chats: dict[int, TLChat] | None = None,
) -> Messages:
    if users is None:
        users = {}
    if chats is None:
        chats = {}

    messages_tl = []
    for message in messages:
        messages_tl.append(await message.to_tl(user))

        if message.author.id not in users:
            users[message.author.id] = await message.author.to_tl(user)
        if message.peer.user is not None and message.peer.user.id not in users:
            users[message.peer.user.id] = await message.peer.user.to_tl(user)
        if message.peer.type is PeerType.CHAT and message.peer.chat_id is not None:
            chat = await message.peer.chat
            chats[chat.id] = await chat.to_tl(user)

    # TODO: MessagesSlice
    return Messages(
        messages=messages_tl,
        chats=list(chats.values()),
        users=list(users.values()),
    )


@handler.on_request(GetHistory)
async def get_history(request: GetHistory, user: User) -> Messages:
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    messages = await get_messages_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset
    )
    if not messages:
        return Messages(messages=[], chats=[], users=[])

    return await _format_messages(user, messages)


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

    return await _format_messages(user, await Message.filter(query))


@handler.on_request(ReadHistory)
async def read_history(request: ReadHistory, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    ex = await ReadState.get_or_none(dialog__peer=peer)
    message = await Message.filter(
        id__lte=min(request.max_id, ex.last_message_id if ex is not None else request.max_id), peer=peer,
    ).order_by("-id").limit(1)
    if message:
        messages_count = await Message.filter(
            id__gt=ex.last_message_id if ex is not None else 0, id__lt=message[0].id, peer=peer,
        ).count()
    else:
        messages_count = 0

    # TODO: save to database
    return AffectedMessages(
        pts=await State.add_pts(user, messages_count),
        pts_count=messages_count,
    )


@handler.on_request(Search)
async def messages_search(request: Search, user: User) -> Messages:
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    from_user_id = None
    if isinstance(request.from_id, InputPeerUser):
        from_user_id = request.from_id.user_id
    elif isinstance(request.from_id, InputPeerSelf):
        from_user_id = user.id

    messages = await get_messages_internal(
        peer, request.max_id, request.min_id, request.offset_id, request.limit, request.add_offset, from_user_id,
        request.min_date, request.max_date, request.q, request.filter
    )

    return await _format_messages(user, messages)


@handler.on_request(GetSearchCounters)
async def get_search_counters(request: GetSearchCounters, user: User):
    if (peer := await Peer.from_input_peer(user, request.peer)) is None:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    return [
        SearchCounter(
            filter=filt,
            count=await _get_messages_query(peer, 0, 0, 0, 0, 0, 0, 0, 0, None, filt).count(),
        ) for filt in request.filters
    ]


@handler.on_request(GetAllDrafts)
async def get_all_drafts(user: User):
    users = {}
    updates = []
    drafts = await MessageDraft.filter(dialog__peer__owner=user).select_related("dialog", "dialog__peer", "dialog__peer__user")
    for draft in drafts:
        peer = draft.dialog.peer
        updates.append(UpdateDraftMessage(peer=peer.to_tl(), draft=draft.to_tl()))
        if peer.user.id not in users:
            users[peer.user.id] = await peer.user.to_tl(user)

    return Updates(
        updates=updates,
        users=list(users.values()),
        chats=[],
        date=int(time()),
        seq=0,
    )


@handler.on_request(SearchGlobal)
async def search_global(request: SearchGlobal, user: User):
    users = {}

    q = user_q = request.q
    if q.startswith("@"):
        user_q = q[1:]
    if username_regex_no_len.match(user_q):
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

    return await _format_messages(user, messages, users)
