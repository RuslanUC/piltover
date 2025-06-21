from datetime import date, timedelta, datetime

from pytz import UTC

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, Contact, Username
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import ContactBirthday, Updates, Contact as TLContact, PeerBlocked, ImportedContact
from piltover.tl.functions.contacts import ResolveUsername, GetBlocked, Search, GetTopPeers, GetStatuses, \
    GetContacts, GetBirthdays, ResolvePhone, AddContact, DeleteContacts, Block, Unblock, Block_136, Unblock_136, \
    ResolveUsername_136, ImportContacts
from piltover.tl.types.contacts import Blocked, Found, TopPeers, Contacts, ResolvedPeer, ContactBirthdays, BlockedSlice, \
    ImportedContacts
from piltover.worker import MessageHandler

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


async def _format_resolved_peer(user: User, resolved: Username) -> ResolvedPeer:
    if resolved.user == user:
        peer, _ = await Peer.get_or_create(owner=user, user=None, type=PeerType.SELF)
    elif resolved.user is not None:
        peer, _ = await Peer.get_or_create(owner=user, user=resolved.user, type=PeerType.USER)
    elif resolved.channel is not None:
        peer, _ = await Peer.get_or_create(owner=user, channel=resolved.channel, type=PeerType.CHANNEL)
    else:  # pragma: no cover
        raise RuntimeError("Unreachable")

    return ResolvedPeer(
        peer=peer.to_tl(),
        chats=[await resolved.channel.to_tl(user)] if resolved.channel is not None else [],
        users=[await resolved.user.to_tl(user)] if resolved.user is not None else [],
    )


async def _format_resolved_peer_by_phone(user: User, resolved: User) -> ResolvedPeer:
    if resolved == user:
        peer, _ = await Peer.get_or_create(owner=user, user=None, type=PeerType.SELF)
    else:
        peer, _ = await Peer.get_or_create(owner=user, user=resolved, type=PeerType.USER)

    return ResolvedPeer(
        peer=peer.to_tl(),
        chats=[],
        users=[await resolved.to_tl(user)],
    )


@handler.on_request(ResolveUsername_136)
@handler.on_request(ResolveUsername)
async def resolve_username(request: ResolveUsername, user: User) -> ResolvedPeer:
    resolved_username = await Username.get_or_none(username=request.username).select_related("user", "channel")
    if resolved_username is None:
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_OCCUPIED")

    return await _format_resolved_peer(user, resolved_username)


@handler.on_request(GetBlocked)
async def get_blocked(request: GetBlocked, user: User) -> Blocked | BlockedSlice:
    limit = max(min(request.limit, 1), 100)
    blocked_query = Peer.filter(
        owner=user, type=PeerType.USER, blocked_at__not_isnull=True,
    ).select_related("user").order_by("-id")
    blocked_peers = await blocked_query.limit(limit).offset(request.offset)
    count = await blocked_query.count()

    peers_blocked = [
        PeerBlocked(peer_id=peer.to_tl(), date=int(peer.blocked_at.timestamp()))
        for peer in blocked_peers
    ]
    users = [await blocked.user.to_tl(user) for blocked in blocked_peers]

    if count > (limit + request.offset):
        return BlockedSlice(
            count=count,
            blocked=peers_blocked,
            chats=[],
            users=users,
        )

    return Blocked(
        blocked=peers_blocked,
        chats=[],
        users=users,
    )


@handler.on_request(Search, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def contacts_search():  # pragma: no cover
    return Found(
        my_results=[],
        results=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetTopPeers, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_top_peers():  # pragma: no cover
    return TopPeers(
        categories=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetStatuses, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_statuses():  # pragma: no cover
    return []


@handler.on_request(GetBirthdays)
async def get_birthdays(user: User) -> ContactBirthdays:
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)
    birthday_peers = await Peer.filter(
        owner=user, user__birthday__gte=yesterday, user__birthday__lte=tomorrow
    ).select_related("user")

    users = []
    birthdays = []
    for peer in birthday_peers:
        if (birthday := await peer.user.to_tl_birthday(user)) is None:
            continue
        birthdays.append(ContactBirthday(contact_id=peer.user.id, birthday=birthday))
        users.append(await peer.user.to_tl(user))

    return ContactBirthdays(
        contacts=birthdays,
        users=users,
    )


@handler.on_request(ResolvePhone)
async def resolve_phone(request: ResolvePhone, user: User) -> ResolvedPeer:
    if (resolved := await User.get_or_none(phone_number=request.phone)) is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_NOT_OCCUPIED")

    return await _format_resolved_peer_by_phone(user, resolved)


@handler.on_request(AddContact)
async def add_contact(request: AddContact, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.id)
    if peer.type is not PeerType.USER:
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
async def delete_contacts(request: DeleteContacts, user: User) -> Updates:
    peers = {}
    for peer_id in request.id:
        try:
            peer = await Peer.from_input_peer_raise(user, peer_id)
        except ErrorRpc:
            continue
        if peer.type is not PeerType.USER:
            continue

        peers[peer.user.id] = peer

    contacts = await Contact.filter(owner=user, target__id__in=list(peers.keys())).values_list("id", "target__id")
    contact_ids = {contact_id for contact_id, _ in contacts}
    user_ids = {user_id for _, user_id in contacts}

    users = [peer.user for user_id, peer in peers.items() if user_id in user_ids]
    await Contact.filter(id__in=contact_ids).delete()

    return await UpdatesManager.add_remove_contact(user, users)


@handler.on_request(Unblock_136)
@handler.on_request(Unblock)
@handler.on_request(Block_136)
@handler.on_request(Block)
async def block_unblock(request: Block, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.id)
    if peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    to_block = isinstance(request, (Block, Block_136))
    if bool(peer.blocked_at) != to_block:
        peer.blocked_at = datetime.now(UTC) if to_block else None
        await peer.save(update_fields=["blocked_at"])
        await UpdatesManager.block_unblock_user(user, peer)

    return True


@handler.on_request(ImportContacts)
async def import_contacts(request: ImportContacts, user: User) -> ImportedContacts:
    to_import = request.contacts[:100]
    to_retry = [contact.client_id for contact in request.contacts[100:]]

    phone_numbers = {
        contact.phone.strip("+"): idx
        for idx, contact in enumerate(to_import)
        if contact.phone.strip("+").isdigit()
    }

    # TODO: check target users privacy settings, if they allow to find them by phone number
    users = {
        contact.id: contact
        for contact in await User.filter(id__not=user.id, phone_number__in=list(phone_numbers.keys()))
    }
    existing_contacts = {
        contact.target_id: contact
        for contact in await Contact.filter(owner=user, id__in=list(users.keys()))
    }

    imported = []

    to_create = []
    to_update = []
    for user_id, contact_user in users.items():
        if user.phone_number not in phone_numbers:
            continue  # TODO: or place in to_retry?

        input_contact = to_import[phone_numbers[user.phone_number]]

        # TODO: fill Contact.phone_number from request?

        if user_id in existing_contacts:
            contact = existing_contacts[user_id]
            if contact.first_name == input_contact.first_name and contact.last_name == input_contact.last_name:
                continue
            contact.first_name = input_contact.first_name
            contact.last_name = input_contact.last_name
            to_update.append(contact)
        else:
            contact = Contact(
                owner=user,
                target=contact_user,
                first_name=input_contact.first_name,
                last_name=input_contact.last_name,
            )
            to_create.append(contact)

        imported.append(ImportedContact(user_id=user_id, client_id=input_contact.client_id))

    await Contact.bulk_update(to_update, fields=["first_name", "last_name"])
    await Contact.bulk_create(to_create)

    # TODO: updates

    return ImportedContacts(
        imported=imported,
        popular_invites=[],
        retry_contacts=to_retry,
        users=[
            await contact_user.to_tl(user)
            for contact_user in users.values()
        ],
    )
