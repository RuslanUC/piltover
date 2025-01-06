from datetime import date, timedelta

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, Contact
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.high_level import MessageHandler
from piltover.tl import ContactBirthday, Updates, Contact as TLContact
from piltover.tl.functions.contacts import ResolveUsername, GetBlocked, Search, GetTopPeers, GetStatuses, \
    GetContacts, GetBirthdays, ResolvePhone, AddContact, DeleteContacts
from piltover.tl.types.contacts import Blocked, Found, TopPeers, Contacts, ResolvedPeer, ContactBirthdays

handler = MessageHandler("contacts")


@handler.on_request(GetContacts)
async def get_contacts(user: User):
    contacts = await Contact.filter(owner=user).select_related("target")

    contacts_tl = []
    users = []

    for contact in contacts:
        if contact.target is None:
            continue

        contacts_tl.append(TLContact(user_id=contact.target.id, mutual=False))
        users.append(await contact.target.to_tl(user))

    return Contacts(
        contacts=contacts_tl,
        saved_count=0,
        users=users,
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


@handler.on_request(AddContact)
async def get_statuses(request: AddContact, user: User) -> Updates:
    if (peer := await Peer.from_input_peer(user, request.id)) is None or peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    contact, created = await Contact.get_or_create(owner=user, target=peer.user, defaults={
        "first_name": request.first_name,
        "last_name": request.last_name,
        # TODO: fill Contact.phone_number from request?
    })
    if not created:
        contact.first_name = request.first_name
        contact.last_name = request.last_name
        await contact.save(update_fields=["first_name", "last_name"])

    # TODO: add_phone_privacy_exception
    return await UpdatesManager.add_remove_contact(user, [peer.user])


@handler.on_request(DeleteContacts)
async def get_statuses(request: DeleteContacts, user: User) -> Updates:
    peers = {}
    for peer_id in request.id:
        try:
            peer = await Peer.from_input_peer(user, peer_id)
        except ErrorRpc:
            continue
        if peer is None or peer.type is not PeerType.USER:
            continue

        peers[peer.user.id] = peer

    contacts = await Contact.filter(owner=user, target__id__in=list(peers.keys())).values_list("id", "target__id")
    contact_ids = {contact_id for contact_id, _ in contacts}
    user_ids = {user_id for _, user_id in contacts}

    users = [peer.user for user_id, peer in peers.items() if user_id in user_ids]
    await Contact.filter(id__in=contact_ids).delete()

    return await UpdatesManager.add_remove_contact(user, users)
