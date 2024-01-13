from piltover.db.models import User
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler, Client
from piltover.tl_new import PeerUser
from piltover.tl_new.functions.contacts import ResolveUsername, GetBlocked, Search, GetTopPeers, GetStatuses, \
    GetContacts
from piltover.tl_new.types.contacts import Blocked, Found, TopPeers, Contacts, ResolvedPeer

handler = MessageHandler("contacts")


# noinspection PyUnusedLocal
@handler.on_request(GetContacts)
async def get_contacts(client: Client, request: GetContacts):
    return Contacts(
        contacts=[],
        saved_count=0,
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(ResolveUsername, True)
async def resolve_username(client: Client, request: ResolveUsername, user: User):
    if (resolved := await User.get_or_none(username=request.username)) is None:
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_OCCUPIED")

    return ResolvedPeer(peer=PeerUser(user_id=resolved.id), chats=[], users=[await resolved.to_tl(user)])


# noinspection PyUnusedLocal
@handler.on_request(GetBlocked)
async def get_blocked(client: Client, request: GetBlocked):
    return Blocked(
        blocked=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(Search)
async def contacts_search(client: Client, request: Search):
    return Found(
        my_results=[],
        results=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetTopPeers)
async def get_top_peers(client: Client, request: GetTopPeers):
    return TopPeers(
        categories=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_request(GetStatuses)
async def get_statuses(client: Client, request: GetStatuses):
    return []
