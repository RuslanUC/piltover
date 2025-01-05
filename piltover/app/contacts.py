from datetime import date, timedelta

from piltover.db.enums import PeerType
from piltover.db.models import User, Peer
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl import ContactBirthday
from piltover.tl.functions.contacts import ResolveUsername, GetBlocked, Search, GetTopPeers, GetStatuses, \
    GetContacts, GetBirthdays, ResolvePhone
from piltover.tl.types.contacts import Blocked, Found, TopPeers, Contacts, ResolvedPeer, ContactBirthdays

handler = MessageHandler("contacts")


@handler.on_request(GetContacts, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_contacts():
    return Contacts(
        contacts=[],
        saved_count=0,
        users=[],
    )


async def _format_resolved_peer(user: User, resolved: User) -> ResolvedPeer:
    if resolved == user:
        peer, _ = await Peer.get_or_create(owner=user, user=None, type=PeerType.SELF)
    else:
        peer, _ = await Peer.get_or_create(owner=user, user=resolved, type=PeerType.USER)

    return ResolvedPeer(
        peer=peer.to_tl(),
        chats=[],
        users=[await resolved.to_tl(user)],
    )


@handler.on_request(ResolveUsername)
async def resolve_username(request: ResolveUsername, user: User):
    if (resolved := await User.get_or_none(username=request.username)) is None:
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_OCCUPIED")

    return await _format_resolved_peer(user, resolved)


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


@handler.on_request(GetBirthdays)
async def get_birthdays(user: User) -> ContactBirthdays:
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)
    birthday_peers = await Peer.filter(
        owner=user, user__birthday__gte=yesterday, user__birthday__lte=tomorrow
    ).select_related("user")

    return ContactBirthdays(
        contacts=[
            ContactBirthday(contact_id=peer.user.id, birthday=peer.user.to_tl_birthday())
            for peer in birthday_peers
        ],
        users=[await peer.user.to_tl(user) for peer in birthday_peers],
    )


@handler.on_request(ResolvePhone)
async def resolve_phone(request: ResolvePhone, user: User) -> ResolvedPeer:
    if (resolved := await User.get_or_none(phonu_number=request.phone)) is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_NOT_OCCUPIED")

    return await _format_resolved_peer(user, resolved)
