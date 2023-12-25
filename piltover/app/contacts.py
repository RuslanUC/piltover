from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import RpcError
from piltover.tl_new.functions.contacts import ResolveUsername, GetBlocked, Search, GetTopPeers, GetStatuses, \
    GetContacts
from piltover.tl_new.types.contacts import Blocked, Found, TopPeers, Contacts

handler = MessageHandler("contacts")


# noinspection PyUnusedLocal
@handler.on_message(GetContacts)
async def get_contacts(client: Client, request: CoreMessage[GetContacts], session_id: int):
    return Contacts(
        contacts=[],
        saved_count=0,
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(ResolveUsername)
async def resolve_username(client: Client, request: CoreMessage[ResolveUsername], session_id: int):
    return RpcError(error_code=400, error_message="USERNAME_NOT_OCCUPIED")


# noinspection PyUnusedLocal
@handler.on_message(GetBlocked)
async def get_blocked(client: Client, request: CoreMessage[GetBlocked], session_id: int):
    return Blocked(
        blocked=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(Search)
async def contacts_search(client: Client, request: CoreMessage[Search], session_id: int):
    return Found(
        my_results=[],
        results=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetTopPeers)
async def get_top_peers(client: Client, request: CoreMessage[GetTopPeers], session_id: int):
    return TopPeers(
        categories=[],
        chats=[],
        users=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetStatuses)
async def get_statuses(client: Client, request: CoreMessage[GetStatuses], session_id: int):
    return []
