from time import time
from typing import cast

from loguru import logger
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.context import request_ctx
from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType
from piltover.db.models import User, Message, State, Update, MessageDraft, Peer, Dialog, Chat, Presence, \
    ChatParticipant, ChannelUpdate, Channel, Poll, DialogFolder, EncryptedChat, UserAuthorization, SecretUpdate, \
    Stickerset, ChatWallpaper
from piltover.db.models._utils import resolve_users_chats, fetch_users_chats
from piltover.session_manager import SessionManager
from piltover.tl import Updates, UpdateNewMessage, UpdateMessageID, UpdateReadHistoryInbox, \
    UpdateEditMessage, UpdateDialogPinned, DraftMessageEmpty, UpdateDraftMessage, \
    UpdatePinnedDialogs, DialogPeer, UpdatePinnedMessages, UpdateUser, UpdateChatParticipants, ChatParticipants, \
    UpdateUserStatus, UpdateUserName, UpdatePeerSettings, PeerSettings, PeerUser, UpdatePeerBlocked, \
    UpdateChat, UpdateDialogUnreadMark, UpdateReadHistoryOutbox, UpdateNewChannelMessage, UpdateChannel, \
    UpdateEditChannelMessage, Long, UpdateDeleteChannelMessages, UpdateFolderPeers, FolderPeer, \
    UpdateChatDefaultBannedRights, UpdateReadChannelInbox, Username as TLUsername, UpdateMessagePoll, \
    UpdateDialogFilterOrder, UpdateDialogFilter, UpdateMessageReactions, UpdateEncryption, UpdateEncryptedChatTyping, \
    UpdateConfig, UpdateRecentReactions, UpdateNewAuthorization, layer, UpdateNewStickerSet, UpdateStickerSets, \
    UpdateStickerSetsOrder, base, UpdatePeerWallpaper, UpdateReadMessagesContents, UpdateNewScheduledMessage, \
    UpdateDeleteScheduledMessages, UpdatePeerHistoryTTL, UpdateDeleteMessages
from piltover.tl.types.internal import LazyChannel, LazyMessage, ObjectWithLazyFields, LazyUser, LazyChat, \
    LazyEncryptedChat, ObjectWithLayerRequirement, FieldWithLayerRequirement


class UpdatesWithDefaults(Updates):
    def __init__(
            self, *, updates: list[base.Update], users: list[base.User] | None = None,
            chats: list[base.Chat] | None = None, date: int | None = None, seq: int | None = None,
    ) -> None:
        super().__init__(
            updates=updates,
            users=users if users is not None else [],
            chats=chats if chats is not None else [],
            date=date if date is not None else int(time()),
            seq=seq if seq is not None else 0,
        )


# TODO: move this module to separate worker

async def send_message(user: User, messages: dict[Peer, Message], ignore_current: bool = True) -> Updates:
    result = None

    for peer, message in messages.items():
        if isinstance(peer.owner, QuerySet):
            await peer.fetch_related("owner")

        users, chats, channels = await resolve_users_chats(
            peer.owner, *message.query_users_chats(Q(), Q(), Q()), {}, {}, {},
        )

        # TODO: also generate UpdateShortMessage / UpdateShortSentMessage

        updates = UpdatesWithDefaults(
            updates=[
                UpdateNewMessage(
                    message=await message.to_tl(peer.owner),
                    pts=await State.add_pts(peer.owner, 1),
                    pts_count=1,
                ),
            ],
            users=list(users.values()),
            chats=[*chats.values(), *channels.values()],
        )

        if message.random_id:
            updates.updates.insert(0, UpdateMessageID(id=message.id, random_id=int(message.random_id)))

        if peer.owner == user:
            result = updates

            read_history_pts = await State.add_pts(user, 1)
            updates.updates.append(UpdateReadHistoryInbox(
                peer=peer.to_tl(),
                max_id=message.id,
                still_unread_count=0,
                pts=read_history_pts,
                pts_count=1,
            ))
            read_history_inbox_args = {"update_type": UpdateType.READ_HISTORY_INBOX, "user": user, "related_id": 0}
            await Update.filter(**read_history_inbox_args).delete()
            await Update.create(**read_history_inbox_args, pts=read_history_pts, related_ids=[message.id, 0])

        ignore_auth_id = request_ctx.get().auth_id if ignore_current and peer.owner == user else None
        await SessionManager.send(updates, peer.owner.id, ignore_auth_id=ignore_auth_id)

    return result


async def send_message_channel(user: User, message: Message) -> Updates:
    message.peer.channel = channel = await message.peer.channel
    channel.pts += 1
    this_pts = channel.pts
    await channel.save(update_fields=["pts"])
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.NEW_MESSAGE,
        related_id=message.id,
        pts=this_pts,
        pts_count=1,
    )

    rel_users, rel_chats, rel_channels = await fetch_users_chats(
        *message.query_users_chats(Q(), Q(), Q()), {}, {}, {},
    )

    lazy_users = [LazyUser(user_id=rel_user.id) for rel_user in rel_users.values()]
    lazy_chats = [LazyChat(chat_id=rel_chat.id) for rel_chat in rel_chats.values()]
    lazy_channels = [LazyChannel(channel_id=rel_channel.id) for rel_channel in rel_channels.values()]

    await SessionManager.send(
        ObjectWithLazyFields(
            object=UpdatesWithDefaults(
                updates=[
                    UpdateNewChannelMessage(
                        message=LazyMessage(message_id=message.id),  # type: ignore
                        pts=channel.pts,
                        pts_count=1,
                    )
                ],
                users=lazy_users,  # type: ignore
                chats=[*lazy_chats, *lazy_channels],  # type: ignore
            ),
            fields=[
                "updates.0.message",
                *(f"users.{i}" for i in range(len(lazy_users))),
                *(f"chats.{i}" for i in range(len(lazy_chats))),
                *(f"chats.{len(lazy_chats) + i}" for i in range(len(lazy_channels)))
            ],
        ),
        channel_id=channel.id,
    )

    users = [await rel_user.to_tl(user) for rel_user in rel_users.values()]
    chats = [await rel_chat.to_tl(user) for rel_chat in rel_chats.values()]
    channels = [await rel_channel.to_tl(user) for rel_channel in rel_channels.values()]

    updates = [
        UpdateNewChannelMessage(
            message=await message.to_tl(user),
            pts=channel.pts,
            pts_count=1,
        ),
    ]

    if message.random_id:
        updates.insert(0, UpdateMessageID(id=message.id, random_id=int(message.random_id)))

    return UpdatesWithDefaults(
        updates=updates,
        users=users,
        chats=[*chats, *channels],
    )


async def send_messages(messages: dict[Peer, list[Message]], user: User | None = None) -> Updates | None:
    result_update = None

    for peer, messages in messages.items():
        peer.owner = await peer.owner
        chats_q = Q()
        users_q = Q()
        channels_q = Q()
        updates = []

        for message in messages:
            users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

            if message.random_id:
                updates.append(UpdateMessageID(id=message.id, random_id=int(message.random_id)))

            updates.append(UpdateNewMessage(
                message=await message.to_tl(peer.owner),
                pts=await State.add_pts(peer.owner, 1),
                pts_count=1,
            ))

        users, chats, channels = await resolve_users_chats(peer.owner, users_q, chats_q, channels_q, {}, {}, {})

        updates = UpdatesWithDefaults(
            updates=updates,
            users=list(users.values()),
            chats=[*chats.values(), *channels.values()],
        )

        await SessionManager.send(updates, peer.owner.id)
        if peer.owner == user:
            result_update = updates

    return result_update


async def send_messages_channel(
        messages: list[Message], channel: Channel, user: User | None = None,
) -> Updates | None:
    update_messages = []
    updates_to_create = []
    chats_q = Q()
    users_q = Q()
    channels_q = Q()

    for message in messages:
        channel.pts += 1
        update_messages.append((message, channel.pts))
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

        updates_to_create.append(ChannelUpdate(
            channel=channel,
            type=ChannelUpdateType.NEW_MESSAGE,
            related_id=message.id,
            pts=channel.pts,
            pts_count=1,
        ))

    await channel.save(update_fields=["pts"])
    await ChannelUpdate.bulk_create(updates_to_create)

    rel_users, rel_chats, rel_channels = await fetch_users_chats(users_q, chats_q, channels_q, {}, {}, {})

    lazy_users = [LazyUser(user_id=rel_user.id) for rel_user in rel_users.values()]
    lazy_chats = [LazyChat(chat_id=rel_chat.id) for rel_chat in rel_chats.values()]
    lazy_channels = [LazyChannel(channel_id=rel_channel.id) for rel_channel in rel_channels.values()]

    await SessionManager.send(
        ObjectWithLazyFields(
            object=UpdatesWithDefaults(
                updates=[
                    UpdateNewChannelMessage(
                        message=LazyMessage(message_id=message.id),  # type: ignore
                        pts=pts,
                        pts_count=len(update_messages),
                    )
                    for message, pts in update_messages
                ],
                users=lazy_users,  # type: ignore
                chats=[*lazy_chats, *lazy_channels],  # type: ignore
            ),
            fields=[
                *(f"updates.{i}.message" for i in range(len(update_messages))),
                *(f"users.{i}" for i in range(len(lazy_users))),
                *(f"chats.{i}" for i in range(len(lazy_chats))),
                *(f"chats.{len(lazy_chats) + i}" for i in range(len(lazy_channels)))
            ],
        ),
        channel_id=channel.id,
    )

    if user is None:
        return None

    users = [await rel_user.to_tl(user) for rel_user in rel_users.values()]
    chats = [await rel_chat.to_tl(user) for rel_chat in rel_chats.values()]
    channels = [await rel_channel.to_tl(user) for rel_channel in rel_channels.values()]

    return UpdatesWithDefaults(
        updates=[
            UpdateNewChannelMessage(
                message=await message.to_tl(user),
                pts=pts,
                pts_count=len(update_messages),
            )
            for message, pts in update_messages
        ],
        users=users,
        chats=[*chats, *channels],
    )


async def delete_messages(user: User | None, messages: dict[User, list[int]]) -> int:
    updates_to_create = []
    user_new_pts = None

    for upd_user, message_ids in messages.items():
        pts_count = len(message_ids)
        new_pts = await State.add_pts(upd_user, pts_count)

        update = Update(
            user=upd_user,
            update_type=UpdateType.MESSAGE_DELETE,
            pts=new_pts,
            related_id=None,
            related_ids=message_ids,
        )
        updates_to_create.append(update)

        await SessionManager.send(
            UpdatesWithDefaults(
                updates=[
                    UpdateDeleteMessages(
                        messages=message_ids,
                        pts=new_pts,
                        pts_count=pts_count,
                    ),
                ],
            ),
            upd_user.id
        )

        if user == upd_user:
            user_new_pts = new_pts

    all_ids = [i for ids in messages.values() for i in ids]
    await Update.filter(related_id__in=all_ids).delete()
    await Update.bulk_create(updates_to_create)

    return user_new_pts


async def delete_messages_channel(channel: Channel, messages: list[int]) -> int:
    channel.pts += len(messages)
    new_pts = channel.pts
    await channel.save(update_fields=["pts"])
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.DELETE_MESSAGES,
        related_id=None,
        extra_data=b"".join([Long.write(message_id) for message_id in messages]),
        pts=new_pts,
        pts_count=len(messages),
    )

    await ChannelUpdate.filter(
        channel=channel, related_id__in=messages,
        type__in=(ChannelUpdateType.NEW_MESSAGE, ChannelUpdateType.EDIT_MESSAGE)
    ).delete()

    await SessionManager.send(
        ObjectWithLazyFields(
            object=UpdatesWithDefaults(
                updates=[
                    UpdateDeleteChannelMessages(
                        channel_id=channel.make_id(),
                        messages=messages,
                        pts=channel.pts,
                        pts_count=1,
                    ),
                ],
                chats=[LazyChannel(channel_id=channel.id)],  # type: ignore
            ),
            fields=["chats.0"],
        ),
        channel_id=channel.id
    )

    return new_pts


async def edit_message(user: User, messages: dict[Peer, Message]) -> Updates:
    updates_to_create = []
    result_update = None

    for peer, message in messages.items():
        if isinstance(peer.owner, QuerySet):
            await peer.fetch_related("owner")

        pts = await State.add_pts(peer.owner, 1)

        updates_to_create.append(
            Update(
                user=peer.owner,
                update_type=UpdateType.MESSAGE_EDIT,
                pts=pts,
                related_id=message.id,
            )
        )

        chats = []
        if message.peer.type is PeerType.CHAT:
            await message.peer.fetch_related("chat")
            chats.append(await message.peer.chat.to_tl(peer.owner))

        update = UpdatesWithDefaults(
            updates=[
                UpdateEditMessage(
                    message=await message.to_tl(peer.owner),
                    pts=pts,
                    pts_count=1,
                )
            ],
            users=[await message.author.to_tl(peer.owner)],
            chats=chats,
        )

        if user.id == peer.owner.id:
            result_update = update

        await SessionManager.send(update, peer.owner.id)

    await Update.bulk_create(updates_to_create)
    return result_update


async def edit_message_channel(user: User, message: Message) -> Updates:
    message.peer.channel = channel = await message.peer.channel
    channel.pts += 1
    this_pts = channel.pts
    await channel.save(update_fields=["pts"])
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.EDIT_MESSAGE,
        related_id=message.id,
        pts=this_pts,
        pts_count=1,
    )

    rel_users, rel_chats, rel_channels = await fetch_users_chats(
        *message.query_users_chats(Q(), Q(), Q()), {}, {}, {},
    )

    lazy_users = [LazyUser(user_id=rel_user.id) for rel_user in rel_users.values()]
    lazy_chats = [LazyChat(chat_id=rel_chat.id) for rel_chat in rel_chats.values()]
    lazy_channels = [LazyChannel(channel_id=rel_channel.id) for rel_channel in rel_channels.values()]

    await SessionManager.send(
        ObjectWithLazyFields(
            object=UpdatesWithDefaults(
                updates=[
                    UpdateEditChannelMessage(
                        message=LazyMessage(message_id=message.id),  # type: ignore
                        pts=channel.pts,
                        pts_count=1,
                    ),
                ],
                users=lazy_users,  # type: ignore
                chats=[*lazy_chats, *lazy_channels],  # type: ignore
            ),
            fields=[
                "updates.0.message",
                *(f"users.{i}" for i in range(len(lazy_users))),
                *(f"chats.{i}" for i in range(len(lazy_chats))),
                *(f"chats.{len(lazy_chats)+i}" for i in range(len(lazy_channels)))
            ],
        ),
        channel_id=channel.id,
    )

    users = [await rel_user.to_tl(user) for rel_user in rel_users.values()]
    chats = [await rel_chat.to_tl(user) for rel_chat in rel_chats.values()]
    channels = [await rel_channel.to_tl(user) for rel_channel in rel_channels.values()]

    return UpdatesWithDefaults(
        updates=[
            UpdateEditChannelMessage(
                message=await message.to_tl(user),
                pts=channel.pts,
                pts_count=1,
            ),
        ],
        users=users,
        chats=[*chats, *channels],
    )


async def pin_dialog(user: User, peer: Peer) -> None:
    new_pts = await State.add_pts(user, 1)
    update = await Update.create(
        user=user,
        update_type=UpdateType.DIALOG_PIN,
        pts=new_pts,
        related_id=peer.id,
    )

    tl_update, users_q, *_ = await update.to_tl(user, Q())
    users_q &= Q(id__not=user.id)

    users, *_ = await resolve_users_chats(user, users_q, None, None, {}, None, None)
    users[user.id] = user

    updates = UpdatesWithDefaults(
        updates=[cast(UpdateDialogPinned, tl_update)],
        users=[await other.to_tl(user) for other in users.values()],
        chats=[await peer.chat.to_tl(user)] if peer.type is PeerType.CHAT else [],
    )

    await SessionManager.send(updates, user.id)


async def update_draft(user: User, peer: Peer, draft: MessageDraft | None) -> None:
    if isinstance(draft, MessageDraft):
        draft = draft.to_tl()
    elif draft is None:
        draft = DraftMessageEmpty()

    new_pts = await State.add_pts(user, 1)
    await Update.create(
        user=user,
        update_type=UpdateType.DRAFT_UPDATE,
        pts=new_pts,
        related_id=peer.id,
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateDraftMessage(peer=peer.to_tl(), draft=draft)],
        users=[await user.to_tl(user)],
        chats=[await peer.chat.to_tl(user)] if peer.type is PeerType.CHAT else [],
    )

    await SessionManager.send(updates, user.id)


async def reorder_pinned_dialogs(user: User, dialogs: list[Dialog]) -> None:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.DIALOG_PIN_REORDER,
        pts=new_pts,
        related_id=None,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdatePinnedDialogs(
                order=[
                    DialogPeer(peer=dialog.peer.to_tl())
                    for dialog in dialogs
                ],
            )
        ],
        users=[await user.to_tl(user)],
        chats=[await dialog.peer.chat.to_tl(user) for dialog in dialogs if dialog.peer.type is PeerType.CHAT],
    )

    await SessionManager.send(updates, user.id)


async def pin_message(user: User, messages: dict[Peer, Message]) -> Updates:
    updates_to_create = []
    result_update = None

    for peer, message in messages.items():
        if isinstance(peer.owner, QuerySet):
            await peer.fetch_related("owner", "chat")

        pts = await State.add_pts(peer.owner, 1)

        updates_to_create.append(
            Update(
                user=peer.owner,
                update_type=UpdateType.MESSAGE_PIN_UPDATE,
                pts=pts,
                related_id=message.id,
            )
        )

        update = UpdatesWithDefaults(
            updates=[
                UpdatePinnedMessages(
                    pinned=message.pinned,
                    peer=message.peer.to_tl(),
                    messages=[message.id],
                    pts=pts,
                    pts_count=1,
                )
            ],
            users=[await message.author.to_tl(peer.owner)],
            chats=[await peer.chat.to_tl(peer.owner)] if peer.type is PeerType.CHAT else [],
        )

        if user.id == peer.owner.id:
            result_update = update

        await SessionManager.send(update, peer.owner.id)

    await Update.bulk_create(updates_to_create)
    return result_update


async def update_user(user: User) -> None:
    updates_to_create = []

    peer: Peer
    async for peer in Peer.filter(Q(user=user) | (Q(owner=user) & Q(type=PeerType.SELF))).select_related("owner"):
        pts = await State.add_pts(peer.owner, 1)

        updates_to_create.append(
            Update(
                user=peer.owner,
                update_type=UpdateType.USER_UPDATE,
                pts=pts,
                related_id=user.id,
            )
        )

        await SessionManager.send(UpdatesWithDefaults(
            updates=[UpdateUser(user_id=user.id)],
            users=[await user.to_tl(peer.owner)],
        ), peer.owner.id)

    await Update.bulk_create(updates_to_create)


# TODO: rename to something like "update_chat_participants"

async def create_chat(user: User, chat: Chat, peers: list[Peer]) -> Updates:
    updates_to_create = []
    result_update = None

    participants = [
        await participant.to_tl()
        for participant in await ChatParticipant.filter(chat=chat).select_related("chat")
    ]
    participant_ids = [participant.user_id for participant in participants]
    users = await User.filter(id__in=participant_ids)

    for peer in peers:
        pts = await State.add_pts(peer.owner, 1)

        updates_to_create.append(
            Update(
                user=peer.owner,
                update_type=UpdateType.CHAT_CREATE,
                pts=pts,
                related_id=chat.id,
                related_ids=participant_ids,
            )
        )

        updates = UpdatesWithDefaults(
            updates=[
                UpdateChatParticipants(
                    participants=ChatParticipants(
                        chat_id=chat.make_id(),
                        participants=participants,
                        version=1,
                    ),
                ),
            ],
            users=[await user_.to_tl(peer.owner) for user_ in users],
            chats=[await chat.to_tl(peer.owner)],
        )

        await SessionManager.send(updates, peer.owner.id)
        if peer.owner == user:
            result_update = updates

    await Update.bulk_create(updates_to_create)
    return result_update


async def update_status(user: User, status: Presence, peers: list[Peer | User]) -> None:
    for peer in peers:
        peer_user = peer.owner if isinstance(peer, Peer) else peer
        updates = UpdatesWithDefaults(
            updates=[
                UpdateUserStatus(
                    user_id=user.id,
                    status=await status.to_tl(peer_user),
                ),
            ],
            users=[await user.to_tl(peer_user)],
        )

        await SessionManager.send(updates, peer_user.id)


async def update_user_name(user: User) -> None:
    updates_to_create = []

    username = await user.get_username()
    username = username.username if username is not None else None

    usernames = [] if not username else [TLUsername(editable=True, active=True, username=username)]
    update = UpdateUserName(
        user_id=user.id, first_name=user.first_name, last_name=user.last_name, usernames=usernames,
    )
    peer: Peer
    async for peer in Peer.filter(Q(user=user) | (Q(owner=user) & Q(type=PeerType.SELF))).select_related("owner"):
        pts = await State.add_pts(peer.owner, 1)

        updates_to_create.append(
            Update(
                user=peer.owner,
                update_type=UpdateType.USER_UPDATE_NAME,
                pts=pts,
                related_id=user.id,
            )
        )

        await SessionManager.send(UpdatesWithDefaults(
            updates=[update],
            users=[await user.to_tl(peer.owner)],
        ), peer.owner.id)

    await Update.bulk_create(updates_to_create)


async def add_remove_contact(user: User, targets: list[User]) -> Updates:
    updates = []
    users = {}
    updates_to_create = []

    for target in targets:
        if target.id in users:
            continue

        pts = await State.add_pts(user, 1)
        updates_to_create.append(Update(
            user=user, update_type=UpdateType.UPDATE_CONTACT, pts=pts, related_id=target.id,
        ))

        updates.append(UpdatePeerSettings(
            peer=PeerUser(user_id=target.id),
            settings=PeerSettings(),
        ))
        users[target.id] = await target.to_tl(user)

    updates = UpdatesWithDefaults(
        updates=updates,
        users=list(users.values()),
    )

    await Update.bulk_create(updates_to_create)
    await SessionManager.send(updates, user.id)

    return updates


async def block_unblock_user(user: User, target: Peer) -> None:
    pts = await State.add_pts(user, 1)
    await Update.create(
        user=user, update_type=UpdateType.UPDATE_BLOCK, pts=pts, related_id=target.user.id,
    )

    await SessionManager.send(UpdatesWithDefaults(
        updates=[
            UpdatePeerBlocked(
                peer_id=target.to_tl(),
                blocked=target.blocked_at is not None,
            ),
        ],
        users=[await target.user.to_tl(user)],
    ), user.id)


async def update_chat(chat: Chat, user: User | None = None) -> Updates | None:
    updates_to_create = []
    update_to_return = None

    peer: Peer
    async for peer in Peer.filter(chat=chat).select_related("owner"):
        pts = await State.add_pts(peer.owner, 1)
        updates_to_create.append(Update(
            user=peer.owner, update_type=UpdateType.UPDATE_CHAT, pts=pts, related_id=chat.id,
        ))

        updates = UpdatesWithDefaults(
            updates=[UpdateChat(chat_id=chat.make_id())],
            chats=[await chat.to_tl(peer.owner)],
        )
        if user == peer.owner:
            update_to_return = updates

        await SessionManager.send(updates, peer.owner.id)

    await Update.bulk_create(updates_to_create)

    return update_to_return


async def update_dialog_unread_mark(user: User, dialog: Dialog) -> None:
    pts = await State.add_pts(user, 1)
    await Update.create(
        user=user, update_type=UpdateType.UPDATE_DIALOG_UNREAD_MARK, pts=pts, related_id=dialog.id,
    )

    users_q, chats_q, channels_q = Peer.query_users_chats_cls(dialog.peer_id, Q(), Q(), Q())
    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    await SessionManager.send(UpdatesWithDefaults(
        updates=[
            UpdateDialogUnreadMark(
                peer=DialogPeer(peer=dialog.peer.to_tl()),
                unread=dialog.unread_mark,
            ),
        ],
        users=list(users.values()),
        chats=[*chats.values(), *channels.values()],
    ), user.id)


async def update_read_history_inbox(peer: Peer, max_id: int, read_count: int, unread_count: int) -> None:
    pts = await State.add_pts(peer.owner, read_count)
    await Update.create(
        user=peer.owner, update_type=UpdateType.READ_INBOX, pts=pts, pts_count=read_count, related_id=peer.id,
        additional_data=[max_id, unread_count],
    )

    users_q, chats_q, channels_q = peer.query_users_chats(Q(), Q(), Q())
    users, chats, channels = await resolve_users_chats(peer.owner, users_q, chats_q, channels_q, {}, {}, {})

    await SessionManager.send(UpdatesWithDefaults(
        updates=[
            UpdateReadHistoryInbox(
                peer=peer.to_tl(),
                max_id=max_id,
                still_unread_count=unread_count,
                pts=pts,
                pts_count=read_count,
            ),
        ],
        users=list(users.values()),
        chats=[*chats.values(), *channels.values()],
    ), peer.owner.id)


async def update_read_history_inbox_channel(peer: Peer, max_id: int, unread_count: int) -> None:
    pts = await State.add_pts(peer.owner, 1)
    await Update.create(
        user=peer.owner, update_type=UpdateType.READ_INBOX, pts=pts, pts_count=1, related_id=peer.id,
        additional_data=[max_id, unread_count],
    )

    users_q, chats_q, channels_q = peer.query_users_chats(Q(), Q(), Q())
    users, chats, channels = await resolve_users_chats(peer.owner, users_q, chats_q, channels_q, {}, {}, {})

    await SessionManager.send(UpdatesWithDefaults(
        updates=[
            UpdateReadChannelInbox(
                channel_id=Channel.make_id_from(peer.channel_id),
                max_id=max_id,
                still_unread_count=unread_count,
                pts=pts,
            ),
        ],
        users=list(users.values()),
        chats=[*chats.values(), *channels.values()],
    ), peer.owner.id)


async def update_read_history_outbox(messages: dict[Peer, tuple[int, int]]) -> None:
    updates_to_create = []

    for peer, (max_id, count) in messages.items():
        pts = await State.add_pts(peer.owner, count)
        updates_to_create.append(Update(
            user=peer.owner, update_type=UpdateType.READ_OUTBOX, pts=pts, pts_count=count, related_id=peer.id,
            additional_data=[max_id],
        ))

        users_q, chats_q, channels_q = peer.query_users_chats(Q(), Q(), Q())
        users, chats, channels = await resolve_users_chats(peer.owner, users_q, chats_q, channels_q, {}, {}, {})

        await SessionManager.send(UpdatesWithDefaults(
            updates=[
                UpdateReadHistoryOutbox(
                    peer=peer.to_tl(),
                    max_id=max_id,
                    pts=pts,
                    pts_count=count,
                ),
            ],
            users=list(users.values()),
            chats=[*chats.values(), *channels.values()],
        ), peer.owner.id)

    await Update.bulk_create(updates_to_create)


async def update_channel(
        channel: Channel, user: User | None = None, send_to_users: list[int] | None = None,
) -> Updates | None:
    channel.pts += 1
    this_pts = channel.pts
    await channel.save(update_fields=["pts"])
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.UPDATE_CHANNEL,
        related_id=None,
        pts=this_pts,
        pts_count=1,
    )

    await SessionManager.send(
        ObjectWithLazyFields(
            object=UpdatesWithDefaults(
                updates=[UpdateChannel(channel_id=channel.make_id())],
                chats=[LazyChannel(channel_id=channel.id)],  # type: ignore
            ),
            fields=["chats.0"],
        ),
        channel_id=channel.id if send_to_users is None else None,
        user_id=send_to_users,
    )

    if user is not None:
        return UpdatesWithDefaults(
            updates=[UpdateChannel(channel_id=channel.make_id())],
            chats=[await channel.to_tl(user)],
        )


async def update_folder_peers(user: User, dialogs: list[Dialog]) -> Updates:
    new_pts = await State.add_pts(user, len(dialogs))

    await Update.create(
        user=user,
        update_type=UpdateType.FOLDER_PEERS,
        pts=new_pts,
        pts_count=len(dialogs),
        related_id=None,
        related_ids=[dialog.peer_id for dialog in dialogs],
    )

    folder_peers = []
    users_q, chats_q, channels_q = Q(), Q(), Q()

    for dialog in dialogs:
        folder_peers.append(FolderPeer(peer=dialog.peer.to_tl(), folder_id=dialog.folder_id.value))
        users_q, chats_q, channels_q = dialog.peer.query_users_chats(users_q, chats_q, channels_q)

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    updates = UpdatesWithDefaults(
        updates=[
            UpdateFolderPeers(
                folder_peers=folder_peers,
                pts=new_pts,
                pts_count=len(dialogs),
            )
        ],
        users=list(users.values()),
        chats=[*chats.values(), *channels.values()],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_chat_default_banned_rights(chat: Chat, user: User | None = None) -> Updates | None:
    updates_to_create = []
    update_to_return = None

    banned_rights = chat.banned_rights.to_tl()

    peer: Peer
    async for peer in Peer.filter(chat=chat).select_related("owner"):
        pts = await State.add_pts(peer.owner, 1)
        updates_to_create.append(Update(
            user=peer.owner, update_type=UpdateType.UPDATE_CHAT_BANNED_RIGHTS, pts=pts, related_id=chat.id,
        ))

        updates = UpdatesWithDefaults(
            updates=[
                UpdateChatDefaultBannedRights(
                    peer=peer.to_tl(),
                    default_banned_rights=banned_rights,
                    version=chat.version,
                )
            ],
            chats=[await chat.to_tl(peer.owner)],
        )
        if user == peer.owner:
            update_to_return = updates

        await SessionManager.send(updates, peer.owner.id)

    await Update.bulk_create(updates_to_create)

    return update_to_return


async def update_channel_for_user(channel: Channel, user: User) -> Updates:
    pts = await State.add_pts(user, 1)
    await Update.create(
        user=user, update_type=UpdateType.UPDATE_CHANNEL, pts=pts, related_id=channel.id,
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateChannel(channel_id=channel.make_id())],
        chats=[await channel.to_tl(user)],
    )

    await SessionManager.send(updates, user.id)
    return updates


async def update_message_poll(poll: Poll, user: User) -> Updates:
    pts = await State.add_pts(user, 1)
    await Update.create(
        user=user, update_type=UpdateType.UPDATE_POLL, pts=pts, related_id=poll.id,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateMessagePoll(
                poll_id=poll.id,
                poll=await poll.to_tl(),
                results=await poll.to_tl_results(user),
            )
        ],
    )

    await SessionManager.send(updates, user.id)
    return updates


async def update_folder(user: User, folder_id: int, folder: DialogFolder | None) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_FOLDER,
        pts=new_pts,
        pts_count=1,
        related_id=folder.id if folder is not None else None,
        related_ids=[folder_id],
    )

    # TODO: fetch users, chats, channels from pinned_peers, include_peers, exclude_peers ?

    updates = UpdatesWithDefaults(
        updates=[
            UpdateDialogFilter(
                id=folder_id,
                filter=await folder.to_tl() if folder is not None else None,
            ),
        ],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_folders_order(user: User, folder_ids: list[int]) -> Updates:
    new_pts = await State.add_pts(user, len(folder_ids))

    await Update.create(
        user=user,
        update_type=UpdateType.FOLDERS_ORDER,
        pts=new_pts,
        pts_count=len(folder_ids),
        related_id=None,
        related_ids=folder_ids,
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateDialogFilterOrder(order=folder_ids)],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_reactions(user: User, messages: list[Message], peer: Peer, send: bool = True) -> Updates:
    users_q, chats_q, channels_q = Q(), Q(), Q()

    for message in messages:
        users_q, chats_q, channels_q = message.query_users_chats(users_q, chats_q, channels_q)

    users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

    updates = UpdatesWithDefaults(
        updates=[
            UpdateMessageReactions(
                peer=peer.to_tl(),
                msg_id=message.id,
                reactions=await message.to_tl_reactions(user),
            ) for message in messages
        ],
        users=list(users.values()),
        chats=[*chats.values(), *channels.values()],
    )

    if send:
        await SessionManager.send(updates, user.id)

    return updates


async def encryption_update(user: User, chat: EncryptedChat) -> None:
    new_pts = await State.add_pts(user, 1)

    await Update.filter(user=user, update_type=UpdateType.UPDATE_ENCRYPTION, related_id=chat.id).delete()
    update = await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_ENCRYPTION,
        pts=new_pts,
        pts_count=1,
        related_id=chat.id,
    )
    logger.trace(f"Sending UPDATE_ENCRYPTION to user {user.id}")

    other_user = chat.from_user if user.id == chat.to_user_id else chat.to_user
    other_user = await other_user

    await SessionManager.send(
        ObjectWithLazyFields(
            object=UpdatesWithDefaults(
                updates=[
                    UpdateEncryption(
                        chat=LazyEncryptedChat(chat_id=chat.id),  # type: ignore
                        date=int(update.date.timestamp()),
                    ),
                ],
                users=[await other_user.to_tl(user)],
            ),
            fields=["updates.0.chat"],
        ),
        user_id=user.id,
    )


async def send_encrypted_update(update: SecretUpdate) -> None:
    logger.trace(
        f"Sending secret update of type {update.type!r} "
        f"to user {update.authorization.user_id} (auth {update.authorization.id})"
    )
    await SessionManager.send(
        UpdatesWithDefaults(updates=[await update.to_tl()]),
        auth_id=update.authorization_id,
    )


async def send_encrypted_typing(chat_id: int, auth_id: int) -> None:
    await SessionManager.send(
        UpdatesWithDefaults(updates=[UpdateEncryptedChatTyping(chat_id=chat_id)]),
        auth_id=auth_id,
    )


async def update_config(user: User) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_CONFIG,
        pts=new_pts,
        pts_count=1,
        related_id=None,
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateConfig()],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_recent_reactions(user: User) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_RECENT_REACTIONS,
        pts=new_pts,
        pts_count=1,
        related_id=None,
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateRecentReactions()],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def new_auth(user: User, auth: UserAuthorization) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.NEW_AUTHORIZATION,
        pts=new_pts,
        pts_count=1,
        related_id=auth.id,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateNewAuthorization(
                unconfirmed=not auth.confirmed,
                hash=auth.tl_hash,
                date=int(auth.created_at.timestamp()),
                device=auth.device_model if auth.device_model != "Unknown" else None,
                location=auth.ip,
            ),
        ],
    )

    await SessionManager.send(
        ObjectWithLayerRequirement(
            object=updates,
            fields=[
                FieldWithLayerRequirement(field="updates.0", min_layer=163, max_layer=layer),
            ],
        ),
        user.id
    )

    return updates


async def new_stickerset(user: User, stickerset: Stickerset) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.NEW_STICKERSET,
        pts=new_pts,
        pts_count=1,
        related_id=stickerset.id,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateNewStickerSet(
                stickerset=await stickerset.to_tl_messages(user),
            ),
        ],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_stickersets(user: User) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_STICKERSETS,
        pts=new_pts,
        pts_count=1,
        related_id=None,
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateStickerSets()],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_stickersets_order(user: User, new_order: list[int]) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_STICKERSETS_ORDER,
        pts=new_pts,
        pts_count=1,
        related_id=None,
        related_ids=new_order,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateStickerSetsOrder(
                order=new_order,
            )
        ],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_chat_wallpaper(user: User, target: User, chat_wallpaper: ChatWallpaper | None) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_CHAT_WALLPAPER,
        pts=new_pts,
        pts_count=1,
        related_id=target.id,
        related_ids=[chat_wallpaper.wallpaper.id] if chat_wallpaper is not None else None,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdatePeerWallpaper(
                wallpaper_overridden=chat_wallpaper.overridden if chat_wallpaper is not None else False,
                peer=PeerUser(user_id=target.id),
                wallpaper=await chat_wallpaper.wallpaper.to_tl(user) if chat_wallpaper is not None else None,
            )
        ],
        users=[await target.to_tl(user)]
    )

    await SessionManager.send(updates, user.id)

    return updates


async def read_messages_contents(user: User, message_ids: list[int]) -> tuple[int, Updates]:
    pts_count = len(message_ids)
    new_pts = await State.add_pts(user, pts_count)

    await Update.create(
        user=user,
        update_type=UpdateType.READ_MESSAGES_CONTENTS,
        pts=new_pts,
        pts_count=pts_count,
        related_id=None,
        related_ids=message_ids,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateReadMessagesContents(
                messages=message_ids,
                pts=new_pts,
                pts_count=pts_count,
                date=int(time()),
            )
        ],
    )

    await SessionManager.send(updates, user.id)

    return new_pts, updates


async def new_scheduled_message(user: User, message: Message) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.NEW_SCHEDULED_MESSAGE,
        pts=new_pts,
        pts_count=1,
        related_id=message.id,
        related_ids=None,
    )

    updates = UpdatesWithDefaults(updates=[UpdateNewScheduledMessage(message=await message.to_tl(user))])

    await SessionManager.send(updates, user.id)

    return updates


async def delete_scheduled_messages(
        user: User, peer: Peer, deleted_message_ids: list[int], sent_message_ids: list[int] | None = None,
) -> Updates:
    pts_count = len(deleted_message_ids)
    new_pts = await State.add_pts(user, pts_count)

    await Update.create(
        user=user,
        update_type=UpdateType.DELETE_SCHEDULED_MESSAGE,
        pts=new_pts,
        pts_count=pts_count,
        related_id=peer.id,
        related_ids=[*deleted_message_ids, *(sent_message_ids if sent_message_ids else ())],
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateDeleteScheduledMessages(
                peer=peer.to_tl(),
                messages=deleted_message_ids,
                sent_messages=sent_message_ids or None,
            )
        ],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_history_ttl(peer: Peer, ttl_days: int) -> Updates:
    peers = [peer]
    peers.extend(await peer.get_opposite())

    result: Updates | None = None

    updates_to_create: list[Update] = []
    updates_to_send: list[tuple[Updates, int]] = []
    for update_peer in peers:
        new_pts = await State.add_pts(update_peer.owner, 1)

        updates_to_create.append(Update(
            user=update_peer.owner,
            update_type=UpdateType.UPDATE_HISTORY_TTL,
            pts=new_pts,
            pts_count=1,
            related_id=peer.id,
            additional_data=[ttl_days],
        ))

        updates = UpdatesWithDefaults(
            updates=[
                UpdatePeerHistoryTTL(
                    peer=update_peer.to_tl(),
                    ttl_period=ttl_days * 86400 if ttl_days else None,
                ),
            ],
        )

        updates_to_send.append((updates, update_peer.owner_id))

        if update_peer == peer:
            result = updates

    await Update.bulk_create(updates_to_create)

    for upd, uid in updates_to_send:
        await SessionManager.send(upd, uid)

    return result
