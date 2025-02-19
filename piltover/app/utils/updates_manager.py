from time import time
from typing import cast

from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType
from piltover.db.models import User, Message, State, Update, MessageDraft, Peer, Dialog, Chat, Presence, \
    ChatParticipant, ChannelUpdate
from piltover.session_manager import SessionManager
from piltover.tl import Updates, UpdateNewMessage, UpdateMessageID, UpdateReadHistoryInbox, \
    UpdateEditMessage, UpdateDialogPinned, DraftMessageEmpty, UpdateDraftMessage, \
    UpdatePinnedDialogs, DialogPeer, UpdatePinnedMessages, UpdateUser, UpdateChatParticipants, ChatParticipants, \
    UpdateUserStatus, UpdateUserName, Username, UpdatePeerSettings, PeerSettings, PeerUser, UpdatePeerBlocked, \
    UpdateChat, UpdateDialogUnreadMark, UpdateReadHistoryOutbox, UpdateNewChannelMessage


# TODO: move UpdatesManager to separate worker
class UpdatesManager:
    @staticmethod
    async def send_message(user: User, messages: dict[Peer, Message]) -> Updates:
        result = None

        for peer, message in messages.items():
            if isinstance(peer.owner, QuerySet):
                await peer.fetch_related("owner")

            users, chats, channels = await message.tl_users_chats(peer.owner, {}, {}, {})

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
        result = None

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

        for to_user in await User.filter(chatparticipants__channel__id=message.peer.channel_id):
            users, chats, channels = await message.tl_users_chats(to_user, {}, {}, {})

            updates = Updates(
                updates=[
                    UpdateNewChannelMessage(
                        message=await message.to_tl(to_user),
                        pts=channel.pts,
                        pts_count=1,
                    ),
                ],
                users=list(users.values()),
                chats=[*chats.values(), *channels.values()],
                date=int(time()),
                seq=0,
            )

            if user == to_user and message.random_id:
                updates.updates.insert(0, UpdateMessageID(id=message.id, random_id=int(message.random_id)))

            if user == to_user:
                result = updates

            await SessionManager.send(updates, to_user.id)

        return result

    @staticmethod
    async def send_messages(messages: dict[Peer, list[Message]], user: User | None = None) -> Updates | None:
        result_update = None

        for peer, messages in messages.items():
            peer.owner = await peer.owner
            chats = {}
            users = {}
            channels = {}
            updates = []

            for message in messages:
                await message.tl_users_chats(peer.owner, users, chats, channels)

                updates.append(UpdateNewMessage(
                    message=await message.to_tl(peer.owner),
                    pts=await State.add_pts(peer.owner, 1),
                    pts_count=1,
                ))

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
                    updates=[await update.to_tl(update_user)],
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

        updates = Updates(updates=[await update.to_tl(user)], users=[], chats=[], date=int(time()), seq=0)
        await SessionManager.send(updates, user.id)

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
    async def pin_dialog(user: User, peer: Peer) -> None:
        new_pts = await State.add_pts(user, 1)
        update = await Update.create(
            user=user,
            update_type=UpdateType.DIALOG_PIN,
            pts=new_pts,
            related_id=peer.id,
        )

        users = {user.id: user}
        tl_update = await update.to_tl(user, users)

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

        usernames = [] if not user.username else [Username(editable=True, active=True, username=user.username)]
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
                    blocked=target.blocked,
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

        users, chats, channels = await dialog.peer.tl_users_chats(user, {}, {}, {})

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

        users, chats, channels = await peer.tl_users_chats(peer.owner, {}, {}, {})

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
    async def update_read_history_outbox(messages: dict[Peer, tuple[int, int]]) -> None:
        updates_to_create = []

        for peer, (max_id, count) in messages.items():
            pts = await State.add_pts(peer.owner, count)
            updates_to_create.append(Update(
                user=peer.owner, update_type=UpdateType.READ_OUTBOX, pts=pts, pts_count=count, related_id=peer.id,
                additional_data=[max_id],
            ))

            users, chats, channels = await peer.tl_users_chats(peer.owner, {}, {}, {})

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
