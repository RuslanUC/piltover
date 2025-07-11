from time import time
from typing import cast

from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType
from piltover.db.models import User, Message, State, Update, MessageDraft, Peer, Dialog, Chat, Presence, \
    ChatParticipant, ChannelUpdate, Channel, Poll, DialogFolder, EncryptedChat, UserAuthorization, SecretUpdate
from piltover.db.models._utils import resolve_users_chats, fetch_users_chats
from piltover.session_manager import SessionManager
from piltover.tl import Updates, UpdateNewMessage, UpdateMessageID, UpdateReadHistoryInbox, \
    UpdateEditMessage, UpdateDialogPinned, DraftMessageEmpty, UpdateDraftMessage, \
    UpdatePinnedDialogs, DialogPeer, UpdatePinnedMessages, UpdateUser, UpdateChatParticipants, ChatParticipants, \
    UpdateUserStatus, UpdateUserName, UpdatePeerSettings, PeerSettings, PeerUser, UpdatePeerBlocked, \
    UpdateChat, UpdateDialogUnreadMark, UpdateReadHistoryOutbox, UpdateNewChannelMessage, UpdateChannel, \
    UpdateEditChannelMessage, Long, UpdateDeleteChannelMessages, UpdateFolderPeers, FolderPeer, \
    UpdateChatDefaultBannedRights, UpdateReadChannelInbox, Username as TLUsername, UpdateMessagePoll, \
    UpdateDialogFilterOrder, UpdateDialogFilter, UpdateMessageReactions, UpdateEncryption, EncryptedChatDiscarded, \
    UpdateEncryptedChatTyping
from piltover.tl.types.internal import LazyChannel, LazyMessage, ObjectWithLazyFields, LazyUser, LazyChat, \
    LazyEncryptedChat


# TODO: move UpdatesManager to separate worker
class UpdatesManager:
    @staticmethod
    async def send_message(user: User, messages: dict[Peer, Message]) -> Updates:
        result = None

        for peer, message in messages.items():
            if isinstance(peer.owner, QuerySet):
                await peer.fetch_related("owner")

            users, chats, channels = await resolve_users_chats(
                peer.owner, *message.query_users_chats(Q(), Q(), Q()), {}, {}, {},
            )

            # TODO: also generate UpdateShortMessage / UpdateShortSentMessage

            updates = Updates(
                updates=[
                    UpdateNewMessage(
                        message=await message.to_tl(peer.owner),
                        pts=await State.add_pts(peer.owner, 1),
                        pts_count=1,
                    ),
                ],
                users=list(users.values()),
                chats=[*chats.values(), *channels.values()],
                date=int(time()),
                seq=0,
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

            await SessionManager.send(updates, peer.owner.id)

        return result

    @staticmethod
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
                object=Updates(
                    updates=[
                        UpdateNewChannelMessage(
                            message=LazyMessage(message_id=message.id),  # type: ignore
                            pts=channel.pts,
                            pts_count=1,
                        )
                    ],
                    users=lazy_users,  # type: ignore
                    chats=[*lazy_chats, *lazy_channels],  # type: ignore
                    date=int(time()),
                    seq=0,
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

        return Updates(
            updates=updates,
            users=users,
            chats=[*chats, *channels],
            date=int(time()),
            seq=0,
        )

    @staticmethod
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

                updates.append(UpdateNewMessage(
                    message=await message.to_tl(peer.owner),
                    pts=await State.add_pts(peer.owner, 1),
                    pts_count=1,
                ))

            users, chats, channels = await resolve_users_chats(peer.owner, users_q, chats_q, channels_q, {}, {}, {})

            updates = Updates(
                updates=updates,
                users=list(users.values()),
                chats=[*chats.values(), *channels.values()],
                date=int(time()),
                seq=0,
            )

            await SessionManager.send(updates, peer.owner.id)
            if peer.owner == user:
                result_update = updates

        return result_update

    @staticmethod
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
                object=Updates(
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
                    date=int(time()),
                    seq=0,
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

        return Updates(
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
            date=int(time()),
            seq=0,
        )

    @staticmethod
    async def delete_messages(user: User, messages: dict[User, list[int]]) -> int:
        updates_to_create = []

        for update_user, message_ids in messages.items():
            if user == update_user:
                continue

            pts_count = len(message_ids)
            pts = await State.add_pts(update_user, pts_count)

            update = Update(
                user=update_user,
                update_type=UpdateType.MESSAGE_DELETE,
                pts=pts,
                related_id=None,
                related_ids=message_ids,
            )
            updates_to_create.append(update)

            await SessionManager.send(
                Updates(
                    updates=[(await update.to_tl(update_user))[0]],
                    users=[],
                    chats=[],
                    date=int(time()),
                    seq=0,
                ),
                update_user.id
            )

        all_ids = [i for ids in messages.values() for i in ids]
        new_pts = await State.add_pts(user, len(all_ids))
        update = Update(
            user=user,
            update_type=UpdateType.MESSAGE_DELETE,
            pts=new_pts,
            related_id=None,
            related_ids=all_ids,
        )
        updates_to_create.append(update)

        await Update.filter(related_id__in=all_ids).delete()
        await Update.bulk_create(updates_to_create)

        updates = Updates(updates=[(await update.to_tl(user))[0]], users=[], chats=[], date=int(time()), seq=0)
        await SessionManager.send(updates, user.id)

        return new_pts

    @staticmethod
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
                object=Updates(
                    updates=[
                        UpdateDeleteChannelMessages(
                            channel_id=channel.id,
                            messages=messages,
                            pts=channel.pts,
                            pts_count=1,
                        ),
                    ],
                    users=[],
                    chats=[LazyChannel(channel_id=channel.id)],  # type: ignore
                    date=int(time()),
                    seq=0,
                ),
                fields=["chats.0"],
            ),
            channel_id=channel.id
        )

        return new_pts

    @staticmethod
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

            update = Updates(
                updates=[
                    UpdateEditMessage(
                        message=await message.to_tl(peer.owner),
                        pts=pts,
                        pts_count=1,
                    )
                ],
                users=[await message.author.to_tl(peer.owner)],
                chats=chats,
                date=int(time()),
                seq=0,
            )

            if user.id == peer.owner.id:
                result_update = update

            await SessionManager.send(update, peer.owner.id)

        await Update.bulk_create(updates_to_create)
        return result_update

    @staticmethod
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
                object=Updates(
                    updates=[
                        UpdateEditChannelMessage(
                            message=LazyMessage(message_id=message.id),  # type: ignore
                            pts=channel.pts,
                            pts_count=1,
                        ),
                    ],
                    users=lazy_users,  # type: ignore
                    chats=[*lazy_chats, *lazy_channels],  # type: ignore
                    date=int(time()),
                    seq=0,
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

        return Updates(
            updates=[
                UpdateEditChannelMessage(
                    message=await message.to_tl(user),
                    pts=channel.pts,
                    pts_count=1,
                ),
            ],
            users=users,
            chats=[*chats, *channels],
            date=int(time()),
            seq=0,
        )

    @staticmethod
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

        updates = Updates(
            updates=[cast(UpdateDialogPinned, tl_update)],
            users=[await other.to_tl(user) for other in users.values()],
            chats=[await peer.chat.to_tl(user)] if peer.type is PeerType.CHAT else [],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)

    @staticmethod
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

        updates = Updates(
            updates=[UpdateDraftMessage(peer=peer.to_tl(), draft=draft)],
            users=[await user.to_tl(user)],
            chats=[await peer.chat.to_tl(user)] if peer.type is PeerType.CHAT else [],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)

    @staticmethod
    async def reorder_pinned_dialogs(user: User, dialogs: list[Dialog]) -> None:
        new_pts = await State.add_pts(user, 1)

        await Update.create(
            user=user,
            update_type=UpdateType.DIALOG_PIN_REORDER,
            pts=new_pts,
            related_id=None,
        )

        updates = Updates(
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
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)

    @staticmethod
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

            update = Updates(
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
                date=int(time()),
                seq=0,
            )

            if user.id == peer.owner.id:
                result_update = update

            await SessionManager.send(update, peer.owner.id)

        await Update.bulk_create(updates_to_create)
        return result_update

    @staticmethod
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

            await SessionManager.send(Updates(
                updates=[UpdateUser(user_id=user.id)],
                users=[await user.to_tl(peer.owner)],
                chats=[],
                date=int(time()),
                seq=0,
            ), peer.owner.id)

        await Update.bulk_create(updates_to_create)

    # TODO: rename to something like "update_chat_participants"
    @staticmethod
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

            updates = Updates(
                updates=[
                    UpdateChatParticipants(
                        participants=ChatParticipants(
                            chat_id=chat.id,
                            participants=participants,
                            version=1,
                        ),
                    ),
                ],
                users=[await user_.to_tl(peer.owner) for user_ in users],
                chats=[await chat.to_tl(peer.owner)],
                date=int(time()),
                seq=0,
            )

            await SessionManager.send(updates, peer.owner.id)
            if peer.owner == user:
                result_update = updates

        await Update.bulk_create(updates_to_create)
        return result_update

    @staticmethod
    async def update_status(user: User, status: Presence, peers: list[Peer | User]) -> None:
        for peer in peers:
            peer_user = peer.owner if isinstance(peer, Peer) else peer
            updates = Updates(
                updates=[
                    UpdateUserStatus(
                        user_id=user.id,
                        status=await status.to_tl(peer_user),
                    ),
                ],
                users=[await user.to_tl(peer_user)],
                chats=[],
                date=int(time()),
                seq=0,
            )

            await SessionManager.send(updates, peer_user.id)

    @staticmethod
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

            await SessionManager.send(Updates(
                updates=[update],
                users=[await user.to_tl(peer.owner)],
                chats=[],
                date=int(time()),
                seq=0,
            ), peer.owner.id)

        await Update.bulk_create(updates_to_create)

    @staticmethod
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

        updates = Updates(
            updates=updates,
            users=list(users.values()),
            chats=[],
            date=int(time()),
            seq=0,
        )

        await Update.bulk_create(updates_to_create)
        await SessionManager.send(updates, user.id)

        return updates

    @staticmethod
    async def block_unblock_user(user: User, target: Peer) -> None:
        pts = await State.add_pts(user, 1)
        await Update.create(
            user=user, update_type=UpdateType.UPDATE_BLOCK, pts=pts, related_id=target.user.id,
        )

        await SessionManager.send(Updates(
            updates=[
                UpdatePeerBlocked(
                    peer_id=target.to_tl(),
                    blocked=target.blocked_at is not None,
                ),
            ],
            users=[await target.user.to_tl(user)],
            chats=[],
            date=int(time()),
            seq=0,
        ), user.id)

    @staticmethod
    async def update_chat(chat: Chat, user: User | None = None) -> Updates | None:
        updates_to_create = []
        update_to_return = None

        peer: Peer
        async for peer in Peer.filter(chat=chat).select_related("owner"):
            pts = await State.add_pts(peer.owner, 1)
            updates_to_create.append(Update(
                user=peer.owner, update_type=UpdateType.UPDATE_CHAT, pts=pts, related_id=chat.id,
            ))

            updates = Updates(
                updates=[UpdateChat(chat_id=chat.id)],
                users=[],
                chats=[await chat.to_tl(peer.owner)],
                date=int(time()),
                seq=0,
            )
            if user == peer.owner:
                update_to_return = updates

            await SessionManager.send(updates, peer.owner.id)

        await Update.bulk_create(updates_to_create)

        return update_to_return

    @staticmethod
    async def update_dialog_unread_mark(user: User, dialog: Dialog) -> None:
        pts = await State.add_pts(user, 1)
        await Update.create(
            user=user, update_type=UpdateType.UPDATE_DIALOG_UNREAD_MARK, pts=pts, related_id=dialog.id,
        )

        users_q, chats_q, channels_q = Peer.query_users_chats_cls(dialog.peer_id, Q(), Q(), Q())
        users, chats, channels = await resolve_users_chats(user, users_q, chats_q, channels_q, {}, {}, {})

        await SessionManager.send(Updates(
            updates=[
                UpdateDialogUnreadMark(
                    peer=DialogPeer(peer=dialog.peer.to_tl()),
                    unread=dialog.unread_mark,
                ),
            ],
            users=list(users.values()),
            chats=[*chats.values(), *channels.values()],
            date=int(time()),
            seq=0,
        ), user.id)

    @staticmethod
    async def update_read_history_inbox(peer: Peer, max_id: int, read_count: int, unread_count: int) -> None:
        pts = await State.add_pts(peer.owner, read_count)
        await Update.create(
            user=peer.owner, update_type=UpdateType.READ_INBOX, pts=pts, pts_count=read_count, related_id=peer.id,
            additional_data=[max_id, unread_count],
        )

        users_q, chats_q, channels_q = peer.query_users_chats(Q(), Q(), Q())
        users, chats, channels = await resolve_users_chats(peer.owner, users_q, chats_q, channels_q, {}, {}, {})

        await SessionManager.send(Updates(
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
            date=int(time()),
            seq=0,
        ), peer.owner.id)

    @staticmethod
    async def update_read_history_inbox_channel(peer: Peer, max_id: int, unread_count: int) -> None:
        pts = await State.add_pts(peer.owner, 1)
        await Update.create(
            user=peer.owner, update_type=UpdateType.READ_INBOX, pts=pts, pts_count=1, related_id=peer.id,
            additional_data=[max_id, unread_count],
        )

        users_q, chats_q, channels_q = peer.query_users_chats(Q(), Q(), Q())
        users, chats, channels = await resolve_users_chats(peer.owner, users_q, chats_q, channels_q, {}, {}, {})

        await SessionManager.send(Updates(
            updates=[
                UpdateReadChannelInbox(
                    channel_id=peer.channel_id,
                    max_id=max_id,
                    still_unread_count=unread_count,
                    pts=pts,
                ),
            ],
            users=list(users.values()),
            chats=[*chats.values(), *channels.values()],
            date=int(time()),
            seq=0,
        ), peer.owner.id)

    @staticmethod
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

            await SessionManager.send(Updates(
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
                date=int(time()),
                seq=0,
            ), peer.owner.id)

        await Update.bulk_create(updates_to_create)

    @staticmethod
    async def update_channel(channel: Channel, user: User | None = None) -> Updates | None:
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
                object=Updates(
                    updates=[UpdateChannel(channel_id=channel.id)],
                    users=[],
                    chats=[LazyChannel(channel_id=channel.id)],  # type: ignore
                    date=int(time()),
                    seq=0,
                ),
                fields=["chats.0"],
            ),
            channel_id=channel.id,
        )

        if user is not None:
            return Updates(
                updates=[UpdateChannel(channel_id=channel.id)],
                users=[],
                chats=[await channel.to_tl(user)],
                date=int(time()),
                seq=0,
            )

    @staticmethod
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

        updates = Updates(
            updates=[
                UpdateFolderPeers(
                    folder_peers=folder_peers,
                    pts=new_pts,
                    pts_count=len(dialogs),
                )
            ],
            users=list(users.values()),
            chats=[*chats.values(), *channels.values()],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)

        return updates

    @staticmethod
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

            updates = Updates(
                updates=[
                    UpdateChatDefaultBannedRights(
                        peer=peer.to_tl(),
                        default_banned_rights=banned_rights,
                        version=chat.version,
                    )
                ],
                users=[],
                chats=[await chat.to_tl(peer.owner)],
                date=int(time()),
                seq=0,
            )
            if user == peer.owner:
                update_to_return = updates

            await SessionManager.send(updates, peer.owner.id)

        await Update.bulk_create(updates_to_create)

        return update_to_return

    @staticmethod
    async def update_channel_for_user(channel: Channel, user: User) -> Updates:
        pts = await State.add_pts(user, 1)
        await Update.create(
            user=user, update_type=UpdateType.UPDATE_CHANNEL, pts=pts, related_id=channel.id,
        )

        updates = Updates(
            updates=[UpdateChannel(channel_id=channel.id)],
            users=[],
            chats=[await channel.to_tl(user)],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)
        return updates

    @staticmethod
    async def update_message_poll(poll: Poll, user: User) -> Updates:
        pts = await State.add_pts(user, 1)
        await Update.create(
            user=user, update_type=UpdateType.UPDATE_POLL, pts=pts, related_id=poll.id,
        )

        updates = Updates(
            updates=[
                UpdateMessagePoll(
                    poll_id=poll.id,
                    poll=await poll.to_tl(),
                    results=await poll.to_tl_results(user),
                )
            ],
            users=[],
            chats=[],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)
        return updates

    @staticmethod
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

        updates = Updates(
            updates=[
                UpdateDialogFilter(
                    id=folder_id,
                    filter=await folder.to_tl() if folder is not None else None,
                ),
            ],
            users=[],
            chats=[],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)

        return updates

    @staticmethod
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

        updates = Updates(
            updates=[UpdateDialogFilterOrder(order=folder_ids)],
            users=[],
            chats=[],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)

        return updates

    @staticmethod
    async def update_reactions(user: User, message: Message, peer: Peer) -> Updates:
        # TODO: create update?

        updates = Updates(
            updates=[
                UpdateMessageReactions(
                    peer=peer.to_tl(),
                    msg_id=message.id,
                    reactions=await message.to_tl_reactions(user),
                )
            ],
            users=[],
            chats=[],
            date=int(time()),
            seq=0,
        )

        await SessionManager.send(updates, user.id)

        return updates

    @staticmethod
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

        other_user = chat.from_user if user.id == chat.to_user_id else chat.to_user
        other_user = await other_user

        await SessionManager.send(
            ObjectWithLazyFields(
                object=Updates(
                    updates=[
                        UpdateEncryption(
                            chat=LazyEncryptedChat(chat_id=chat.id),  # type: ignore
                            date=int(update.date.timestamp()),
                        ),
                    ],
                    users=[await other_user.to_tl(user)],
                    chats=[],
                    date=int(time()),
                    seq=0,
                ),
                fields=["updates.0.chat"],
            ),
            user_id=user.id,
        )

    @staticmethod
    async def send_encrypted_update(update: SecretUpdate) -> None:
        await SessionManager.send(
            Updates(
                updates=[await update.to_tl()],
                users=[],
                chats=[],
                date=int(time()),
                seq=0,
            ),
            auth_id=update.authorization_id,
        )

    @staticmethod
    async def send_encrypted_typing(chat_id: int, auth_id: int) -> None:
        await SessionManager.send(
            Updates(
                updates=[
                    UpdateEncryptedChatTyping(chat_id=chat_id)
                ],
                users=[],
                chats=[],
                date=int(time()),
                seq=0,
            ),
            auth_id=auth_id,
        )
