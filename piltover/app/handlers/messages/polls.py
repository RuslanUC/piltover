import base64

from tortoise.expressions import Q

import piltover.app.utils.updates_manager as upd
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, Message, PollAnswer, PollVote
from piltover.db.models.message import append_channel_min_message_id_to_query_maybe
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import Long, PeerUser, MessagePeerVoteInputOption, MessagePeerVote, Updates
from piltover.tl.functions.messages import GetPollResults, SendVote, GetPollVotes
from piltover.tl.types.messages import VotesList
from piltover.worker import MessageHandler

handler = MessageHandler("messages.polls")


@handler.on_request(GetPollResults, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_poll_results(request: GetPollResults, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is PeerType.CHANNEL:
        query = Q(peer__type=PeerType.CHANNEL, peer__owner=None, peer__channel=peer.channel)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)
    else:
        query = Q(peer=peer)

    message = await Message.get_or_none(query & Q(id=request.msg_id)).select_related("media", "media__poll")
    if message is None or message.media is None or message.media.poll is None:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_ID_INVALID")

    return await upd.update_message_poll(message.media.poll, user)


@handler.on_request(GetPollVotes, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_poll_votes(request: GetPollVotes, user: User) -> VotesList:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is PeerType.CHANNEL:
        raise ErrorRpc(error_code=403, error_message="BROADCAST_FORBIDDEN")

    message = await Message.get_or_none(peer=peer, id=request.id).select_related("media", "media__poll")
    if message is None or message.media is None or message.media.poll is None:
        raise ErrorRpc(error_code=400, error_message="MSG_ID_INVALID")
    if not message.media.poll.public_voters:
        raise ErrorRpc(error_code=403, error_message="BROADCAST_FORBIDDEN")
    if not await PollVote.filter(answer__poll=message.media.poll, user=user).exists():
        raise ErrorRpc(error_code=403, error_message="POLL_VOTE_REQUIRED")

    sel_related = ["user"]
    query = Q(answer__poll=message.media.poll, hidden=False)
    if request.option is not None:
        if (option := await PollAnswer.get_or_none(poll=message.media.poll, option=request.option)) is None:
            raise ErrorRpc(error_code=403, error_message="MSG_ID_INVALID")
        query &= Q(answer=option)
    else:
        sel_related.append("answer")

    total_count = await PollVote.filter(query).count()

    if request.offset:
        offset_id = Long.read_bytes(base64.b64decode(request.offset))
        query &= Q(id__lt=offset_id)

    limit = max(min(request.limit, 100), 1)
    votes = await PollVote.filter(query).limit(limit).order_by("-id").select_related(*sel_related)
    if not votes:
        return VotesList(count=total_count, votes=[], chats=[], users=[], next_offset="")

    users = {}
    votes_tl = []

    for vote in votes:
        peer = PeerUser(user_id=vote.user.id)
        vote_date = int(vote.voted_at.timestamp())

        if vote.user.id not in users:
            users[vote.user.id] = await vote.user.to_tl(user)

        if request.option:
            votes_tl.append(MessagePeerVoteInputOption(peer=peer, date=vote_date))
        else:
            votes_tl.append(MessagePeerVote(peer=peer, date=vote_date, option=vote.answer.option))

    has_more = await PollVote.filter(query & Q(id__lt=votes[-1].id)).exists()

    return VotesList(
        count=total_count,
        votes=votes_tl,
        chats=[],
        users=list(users.values()),
        next_offset=base64.b64encode(Long.write(votes[-1].id)).decode("utf8") if has_more else "",
    )


@handler.on_request(SendVote, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def send_vote(request: SendVote, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.peer)
    if peer.type is PeerType.CHANNEL:
        query = Q(peer__type=PeerType.CHANNEL, peer__owner=None, peer__channel=peer.channel)
        query = await append_channel_min_message_id_to_query_maybe(peer, query)
    else:
        query = Q(peer=peer)

    message = await Message.get_or_none(query & Q(id=request.msg_id)).select_related("media", "media__poll")
    if message is None or message.media is None or message.media.poll is None:
        raise ErrorRpc(error_code=400, error_message="MSG_ID_INVALID")
    if message.media.poll.is_closed_fr:
        raise ErrorRpc(error_code=400, error_message="MESSAGE_POLL_CLOSED")
    if not request.options:
        vote_ids = await PollVote.filter(answer__poll=message.media.poll, user=user).values_list("id", flat=True)
        if not vote_ids:
            raise ErrorRpc(error_code=400, error_message="OPTION_INVALID")
        await PollVote.filter(id__in=vote_ids).delete()
        return await upd.update_message_poll(message.media.poll, user)
    if len(request.options) > 1 and not message.media.poll.multiple_choices:
        raise ErrorRpc(error_code=400, error_message="OPTIONS_TOO_MUCH")

    answer: PollAnswer
    options = {answer.option: answer async for answer in PollAnswer.filter(poll=message.media.poll)}

    votes_to_create = []
    for option in request.options:
        if option not in options:
            raise ErrorRpc(error_code=400, error_message="OPTION_INVALID")
        if option in votes_to_create:
            continue
        votes_to_create.append(PollVote(user=user, answer=options[option], hidden=peer.type is PeerType.CHANNEL))

    await PollVote.bulk_create(votes_to_create)
    await message.remove_from_cache(user)

    return await upd.update_message_poll(message.media.poll, user)
