from piltover.db.enums import PeerType
from piltover.db.models import User, Peer
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl.functions.contacts import ResolveUsername, GetBlocked, Search, GetTopPeers, GetStatuses, \
    GetContacts, GetBirthdays
from piltover.tl.types.contacts import Blocked, Found, TopPeers, Contacts, ResolvedPeer, ContactBirthdays

handler = MessageHandler("contacts")


@handler.on_request(GetContacts, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_contacts():
    return Contacts(
        contacts=[],
        saved_count=0,
        users=[],
    )


@handler.on_request(ResolveUsername)
async def resolve_username(request: ResolveUsername, user: User):
    if (resolved := await User.get_or_none(username=request.username)) is None:
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_OCCUPIED")

    if resolved == user:
        peer, _ = await Peer.get_or_create(owner=user, user=None, type=PeerType.SELF)
    else:
        peer, _ = await Peer.get_or_create(owner=user, user=resolved, type=PeerType.USER)

    return ResolvedPeer(
        peer=peer.to_tl(),
        chats=[],
        users=[await resolved.to_tl(user)],
    )


@handler.on_request(GetBlocked, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_blocked():
    return Blocked(
        blocked=[],
        chats=[],
        users=[],
    )


@handler.on_request(Search, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def contacts_search():
    return Found(
        my_results=[],
        results=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetTopPeers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_top_peers():
    return TopPeers(
        categories=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetStatuses, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_statuses():
    return []


@handler.on_request(GetBirthdays, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_birthdays():
    return ContactBirthdays(
        contacts=[],
        users=[],
    )

