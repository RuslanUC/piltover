import hmac
from base64 import urlsafe_b64encode, urlsafe_b64decode
from datetime import date, timedelta, datetime
from hashlib import sha256
from time import time

from pytz import UTC
from tortoise.expressions import Q, Subquery

import piltover.app.utils.updates_manager as upd
from piltover.app_config import AppConfig
from piltover.db.enums import PeerType, PrivacyRuleKeyType
from piltover.db.models import User, Peer, Contact, Username, Dialog, Presence, Channel, PrivacyRuleException, \
    PrivacyRule
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import ContactBirthday, Updates, Contact as TLContact, PeerBlocked, ImportedContact, \
    ExportedContactToken, Long, User as TLUser, TLObjectVector, PeerUser, ContactStatus, PeerChannel
from piltover.tl.functions.contacts import ResolveUsername, GetBlocked, Search, GetTopPeers, GetStatuses, \
    GetContacts, GetBirthdays, ResolvePhone, AddContact, DeleteContacts, Block, Unblock, Block_133, Unblock_133, \
    ResolveUsername_133, ImportContacts, ExportContactToken, ImportContactToken
from piltover.tl.types.contacts import Blocked, Found, TopPeers, Contacts, ResolvedPeer, ContactBirthdays, \
    BlockedSlice, ImportedContacts
from piltover.worker import MessageHandler

handler = MessageHandler("contacts")


@handler.on_request(GetContacts, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_contacts(user: User):
    contacts = await Contact.filter(owner=user, target_id__not_isnull=True).select_related("target")

    contacts_tl = []
    users_to_tl = []

    for contact in contacts:
        contacts_tl.append(TLContact(user_id=contact.target.id, mutual=False))
        users_to_tl.append(contact.target)

    return Contacts(
        contacts=contacts_tl,
        saved_count=0,
        users=await User.to_tl_bulk(users_to_tl),
    )


async def _format_resolved_peer(user: User, resolved: Username) -> ResolvedPeer:
    if resolved.user == user:
        peer = await Peer.get(owner=user, user=user, type=PeerType.SELF)
    elif resolved.user is not None:
        peer, _ = await Peer.get_or_create(owner=user, user=resolved.user, type=PeerType.USER)
    elif resolved.channel is not None:
        peer, _ = await Peer.get_or_create(owner=user, channel=resolved.channel, type=PeerType.CHANNEL)
    else:  # pragma: no cover
        raise RuntimeError("Unreachable")

    await Dialog.get_or_create_hidden(peer)

    return ResolvedPeer(
        peer=peer.to_tl(),
        chats=[await resolved.channel.to_tl()] if resolved.channel is not None else [],
        users=[await resolved.user.to_tl()] if resolved.user is not None else [],
    )


async def _format_resolved_peer_by_phone(user: User, resolved: User) -> ResolvedPeer:
    if resolved == user:
        peer = await Peer.get(owner=user, user=user, type=PeerType.SELF)
    else:
        peer, _ = await Peer.get_or_create(owner=user, user=resolved, type=PeerType.USER)

    return ResolvedPeer(
        peer=peer.to_tl(),
        chats=[],
        users=[await resolved.to_tl()],
    )


@handler.on_request(ResolveUsername_133)
@handler.on_request(ResolveUsername)
async def resolve_username(request: ResolveUsername, user: User) -> ResolvedPeer:
    resolved_username = await Username.get_or_none(username=request.username).select_related("user", "channel")
    if resolved_username is None:
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_OCCUPIED")

    return await _format_resolved_peer(user, resolved_username)


@handler.on_request(GetBlocked, ReqHandlerFlags.BOT_NOT_ALLOWED)
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
    users = await User.to_tl_bulk([blocked.user for blocked in blocked_peers])

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


@handler.on_request(Search, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def contacts_search(request: Search, user: User) -> Found:
    limit = max(1, min(100, request.limit))

    results = await Username.filter(
        user_id__not_in=Subquery(Contact.filter(owner=user).values("target_id")),
        user_id__not=user.id,
    ).filter(
        Q(
            username__icontains=request.q,
            user__first_name__icontains=request.q,
            user__last_name__icontains=request.q,
            join_type=Q.OR,
          )
    ).select_related("user", "channel").limit(limit)

    peers = []
    users = []
    channels = []

    for result in results:
        if result.user is not None:
            peers.append(PeerUser(user_id=result.user_id))
            users.append(result.user)
        elif result.channel is not None:
            peers.append(PeerChannel(channel_id=Channel.make_id_from(result.channel_id)))
            channels.append(result.channel)
        else:
            raise Unreachable

    users_by_id = {result_user.id: result_user for result_user in users}
    channels_by_id = {result_channel.id: result_channel for result_channel in channels}
    for existing_peer in await Peer.filter(
        Q(join_type=Q.OR, user_id__in=list(users_by_id.keys()), channel_id__in=list(channels_by_id.keys())),
        owner=user,
    ):
        if existing_peer.type is PeerType.USER:
            del users_by_id[existing_peer.user_id]
        else:
            del channels_by_id[existing_peer.channel_id]

    await Peer.bulk_create([
        *(
            Peer(owner=user, type=PeerType.USER, user=result_user) for result_user in users_by_id.values()
        ),
        *(
            Peer(owner=user, type=PeerType.CHANNEL, channel=result_channel) for result_channel in channels_by_id.values()
        ),
    ])

    return Found(
        my_results=[],
        results=peers,
        chats=await Channel.to_tl_bulk(channels),
        users=await User.to_tl_bulk(users),
    )


@handler.on_request(GetTopPeers, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_top_peers():  # pragma: no cover
    # TODO: implement GetTopPeers
    return TopPeers(
        categories=[],
        chats=[],
        users=[],
    )


@handler.on_request(GetStatuses, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_statuses(user: User) -> list[ContactStatus]:
    statuses = await Presence.filter(user_id__in=Subquery(
        Contact.filter(owner=user).values_list("target_id", flat=True)
    ))

    return TLObjectVector([
        ContactStatus(user_id=status.user_id, status=await status.to_tl(None))
        for status in statuses
    ])


@handler.on_request(GetBirthdays, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_birthdays(user: User) -> ContactBirthdays:
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)
    birthday_peers = await Peer.filter(
        owner=user, user__birthday__gte=yesterday, user__birthday__lte=tomorrow
    ).select_related("user")

    privacyrules = await PrivacyRule.has_access_to_bulk(
        users=[peer.user for peer in birthday_peers],
        user=user,
        keys=[PrivacyRuleKeyType.BIRTHDAY],
    )

    users_to_tl = []
    birthdays = []
    for peer in birthday_peers:
        if not privacyrules[peer.user_id][PrivacyRuleKeyType.BIRTHDAY]:
            continue
        birthdays.append(ContactBirthday(
            contact_id=peer.user.id,
            birthday=peer.user.to_tl_birthday_noprivacycheck(),
        ))
        users_to_tl.append(peer.user)

    return ContactBirthdays(
        contacts=birthdays,
        users=await User.to_tl_bulk(users_to_tl),
    )


@handler.on_request(ResolvePhone, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def resolve_phone(request: ResolvePhone, user: User) -> ResolvedPeer:
    if (resolved := await User.get_or_none(phone_number=request.phone)) is None:
        raise ErrorRpc(error_code=400, error_message="PHONE_NOT_OCCUPIED")

    # TODO: dont allow user to resolve phone if target user disallowed this via privacy rules

    return await _format_resolved_peer_by_phone(user, resolved)


@handler.on_request(AddContact, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def add_contact(request: AddContact, user: User) -> Updates:
    peer = await Peer.from_input_peer_raise(user, request.id)
    if peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    await Contact.update_or_create(owner=user, target=peer.user, defaults={
        "first_name": request.first_name,
        "last_name": request.last_name,
        "known_phone_number": request.phone or None,
    })

    if request.add_phone_privacy_exception:
        rule = await PrivacyRule.get_or_create(user=user, key=PrivacyRuleKeyType.PHONE_NUMBER, defaults={
            "allow_all": False,
            "allow_contacts": False,
        })
        await PrivacyRuleException.update_or_create(rule=rule, user=peer.user, defaults={
            "allow": True,
        })

    return await upd.add_remove_contact(user, [peer.user])


@handler.on_request(DeleteContacts, ReqHandlerFlags.BOT_NOT_ALLOWED)
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

    contacts = await Contact.filter(owner=user, target_id__in=list(peers.keys())).values_list("id", "target_id")
    contact_ids = {contact_id for contact_id, _ in contacts}
    user_ids = {user_id for _, user_id in contacts}

    users = [peer.user for user_id, peer in peers.items() if user_id in user_ids]
    await Contact.filter(id__in=contact_ids).delete()

    return await upd.add_remove_contact(user, users)


@handler.on_request(Unblock_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(Unblock, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(Block_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(Block, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def block_unblock(request: Block, user: User) -> bool:
    peer = await Peer.from_input_peer_raise(user, request.id)
    if peer.type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    to_block = isinstance(request, (Block, Block_133))
    if bool(peer.blocked_at) != to_block:
        peer.blocked_at = datetime.now(UTC) if to_block else None
        await peer.save(update_fields=["blocked_at"])
        await upd.block_unblock_user(user, peer)

    return True


@handler.on_request(ImportContacts, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def import_contacts(request: ImportContacts, user: User) -> ImportedContacts:
    to_import = request.contacts[:100]
    to_retry = [contact.client_id for contact in request.contacts[100:]]

    phone_numbers = {
        contact.phone.strip("+"): idx
        for idx, contact in enumerate(to_import)
        if contact.phone.strip("+").isdigit()
    }

    # TODO: still create contact if user does not exist ?

    users = {
        contact.id: contact
        for contact in await User.filter(id__not=user.id, phone_number__in=list(phone_numbers.keys()))
    }
    existing_contacts = {
        contact.target_id: contact
        for contact in await Contact.filter(owner=user, target_id__in=list(users.keys()))
    }
    not_allowed = await PrivacyRule.has_access_to_bulk(users.values(), user, [PrivacyRuleKeyType.ADDED_BY_PHONE])
    for user_id, privacy in not_allowed.items():
        if not privacy[PrivacyRuleKeyType.ADDED_BY_PHONE] and user_id in users:
            del users[user_id]

    imported = []

    to_create = []
    to_update = []
    for user_id, contact_user in users.items():
        if user.phone_number not in phone_numbers:
            continue  # TODO: or place in to_retry?

        input_contact = to_import[phone_numbers[user.phone_number]]

        if user_id in existing_contacts:
            contact = existing_contacts[user_id]
            if contact.first_name == input_contact.first_name and contact.last_name == input_contact.last_name:
                continue
            contact.first_name = input_contact.first_name
            contact.last_name = input_contact.last_name
            contact.known_phone_number = user.phone_number
            to_update.append(contact)
        else:
            contact = Contact(
                owner=user,
                target=contact_user,
                first_name=input_contact.first_name,
                last_name=input_contact.last_name,
                known_phone_number=user.phone_number
            )
            to_create.append(contact)

        imported.append(ImportedContact(user_id=user_id, client_id=input_contact.client_id))

    await Contact.bulk_update(to_update, fields=["first_name", "last_name", "known_phone_number"])
    await Contact.bulk_create(to_create)

    # TODO: updates?

    return ImportedContacts(
        imported=imported,
        popular_invites=[],
        retry_contacts=to_retry,
        users=await User.to_tl_bulk(users.values()),
    )


@handler.on_request(ExportContactToken, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def export_contact_token(user: User) -> ExportedContactToken:
    created_at = int(time())
    payload = Long.write(user.id) + Long.write(created_at)

    token_bytes = payload + hmac.new(AppConfig.HMAC_KEY, payload, sha256).digest()
    token = urlsafe_b64encode(token_bytes).decode("utf8")

    return ExportedContactToken(
        url=f"tg://contact?token={token}",
        expires=created_at + AppConfig.CONTACT_TOKEN_EXPIRE_SECONDS,
    )


@handler.on_request(ImportContactToken, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def import_contact_token(request: ImportContactToken, user: User) -> TLUser:
    try:
        token_bytes = urlsafe_b64decode(request.token)
    except ValueError:
        raise ErrorRpc(error_code=400, error_message="IMPORT_TOKEN_INVALID", reason="invalid token")

    if len(token_bytes) != (8 + 8 + 256 // 8):
        raise ErrorRpc(error_code=400, error_message="IMPORT_TOKEN_INVALID", reason="length is invalid")

    target_user_id = Long.read_bytes(token_bytes[:8])
    created_at = Long.read_bytes(token_bytes[8:16])
    payload = token_bytes[:16]
    signature = token_bytes[16:]

    if (created_at + AppConfig.CONTACT_TOKEN_EXPIRE_SECONDS) < time():
        raise ErrorRpc(error_code=400, error_message="IMPORT_TOKEN_INVALID", reason="expired")

    if signature != hmac.new(AppConfig.HMAC_KEY, payload, sha256).digest():
        raise ErrorRpc(error_code=400, error_message="IMPORT_TOKEN_INVALID", reason="invalid signature")

    if (target_user := await User.get_or_none(id=target_user_id, deleted=False)) is None:
        raise ErrorRpc(error_code=400, error_message="IMPORT_TOKEN_INVALID", reason="user does not exist")

    if target_user != user:
        await Peer.get_or_create(owner=user, user=target_user, type=PeerType.USER)

    return await target_user.to_tl()


# TODO: contacts.GetContactIDs
# TODO: contacts.GetSaved ?
