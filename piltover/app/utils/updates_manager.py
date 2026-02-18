from time import time
from typing import overload

from loguru import logger
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from piltover.context import request_ctx
from piltover.db.enums import UpdateType, PeerType, ChannelUpdateType, NotifySettingsNotPeerType
from piltover.db.models import User, State, Update, MessageDraft, Peer, Dialog, Chat, Presence, \
    ChatParticipant, ChannelUpdate, Channel, Poll, DialogFolder, EncryptedChat, UserAuthorization, SecretUpdate, \
    Stickerset, ChatWallpaper, CallbackQuery, PeerNotifySettings, InlineQuery, SavedDialog, PrivacyRule, MessageRef, \
    PhoneCall
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
    UpdateDeleteScheduledMessages, UpdatePeerHistoryTTL, UpdateDeleteMessages, UpdateBotCallbackQuery, UpdateUserPhone, \
    UpdateNotifySettings, UpdateSavedGifs, UpdateBotInlineQuery, UpdateRecentStickers, UpdateFavedStickers, \
    UpdateSavedDialogPinned, UpdatePinnedSavedDialogs, UpdatePrivacy, UpdateChannelReadMessagesContents, \
    UpdateChannelAvailableMessages, UpdatePhoneCall, UpdatePhoneCallSignalingData, UpdateReadChannelOutbox
from piltover.tl.to_format import DumbChannelMessageToFormat
from piltover.tl.types.account import PrivacyRules
from piltover.tl.types.internal import ObjectWithLayerRequirement, FieldWithLayerRequirement
from piltover.utils.users_chats_channels import UsersChatsChannels


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

async def send_message(user: User | None, messages: dict[Peer, MessageRef], ignore_current: bool = True) -> Updates:
    result = None

    ucc = UsersChatsChannels()
    ucc.add_message(next(iter(messages.values())).content_id)
    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]
    updates_to_create = []

    for peer, message in messages.items():
        # TODO: also generate UpdateShortMessage / UpdateShortSentMessage ?

        if message.random_id:
            updates_to_create.append(Update(
                update_type=UpdateType.UPDATE_MESSAGE_ID,
                pts=await State.add_pts(peer.owner, 1),
                pts_count=1,
                related_id=message.id,
                related_ids=[message.random_id],
                user=peer.owner,
            ))

        new_message_pts = await State.add_pts(peer.owner, 1)
        updates_to_create.append(Update(
            update_type=UpdateType.NEW_MESSAGE,
            pts=new_message_pts,
            pts_count=1,
            related_id=message.id,
            user=peer.owner,
        ))

        updates = UpdatesWithDefaults(
            updates=[
                UpdateNewMessage(
                    message=await message.to_tl(peer.owner),
                    pts=new_message_pts,
                    pts_count=1,
                ),
            ],
            users=users,
            chats=chats_and_channels,
        )

        if message.random_id:
            updates.updates.insert(0, UpdateMessageID(id=message.id, random_id=message.random_id))

        if peer.owner == user:
            result = updates

        ignore_auth_id = request_ctx.get().auth_id if ignore_current and peer.owner == user else None
        await SessionManager.send(updates, peer.owner.id, ignore_auth_id=ignore_auth_id)

    if updates_to_create:
        await Update.bulk_create(updates_to_create)

    return result


async def send_message_channel(user: User, channel: Channel, message: MessageRef) -> Updates:
    new_pts = await channel.add_pts(1)
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.NEW_MESSAGE,
        related_id=message.id,
        pts=new_pts,
        pts_count=1,
    )

    ucc = UsersChatsChannels()
    ucc.add_message(message.content_id)
    users, chats, channels = await ucc.resolve()

    chats_and_channels = [*chats, *channels]

    await SessionManager.send(
        UpdatesWithDefaults(
            updates=[
                UpdateNewChannelMessage(
                    message=DumbChannelMessageToFormat(id=message.id),
                    pts=new_pts,
                    pts_count=1,
                )
            ],
            users=users,
            chats=chats_and_channels,
        ),
        channel_id=channel.id,
    )

    updates = [
        UpdateNewChannelMessage(
            message=await message.to_tl(user),
            pts=new_pts,
            pts_count=1,
        ),
    ]

    if message.random_id:
        updates.insert(0, UpdateMessageID(id=message.id, random_id=message.random_id))

    return UpdatesWithDefaults(
        updates=updates,
        users=users,
        chats=chats_and_channels,
    )


async def send_messages(messages: dict[Peer, list[MessageRef]], user: User | None = None) -> Updates | None:
    result_update = None

    ucc = UsersChatsChannels()
    for message in next(iter(messages.values())):
        ucc.add_message(message.content_id)

    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]
    updates_to_create = []

    for peer, messages in messages.items():
        # TODO: dont fetch peer.owner? probably should be prefetched outside of the function
        peer.owner = await peer.owner
        updates = []

        for message in messages:
            if message.random_id:
                updates_to_create.append(Update(
                    update_type=UpdateType.UPDATE_MESSAGE_ID,
                    pts=await State.add_pts(peer.owner, 1),
                    pts_count=1,
                    related_id=message.id,
                    related_ids=[message.random_id],
                    user=peer.owner,
                ))

            new_message_pts = await State.add_pts(peer.owner, 1)
            updates_to_create.append(Update(
                update_type=UpdateType.NEW_MESSAGE,
                pts=new_message_pts,
                pts_count=1,
                related_id=message.id,
                user=peer.owner,
            ))

            if message.random_id:
                updates.append(UpdateMessageID(id=message.id, random_id=message.random_id))

            updates.append(UpdateNewMessage(
                message=await message.to_tl(peer.owner),
                pts=new_message_pts,
                pts_count=1,
            ))

        updates = UpdatesWithDefaults(
            updates=updates,
            users=users,
            chats=chats_and_channels,
        )

        await SessionManager.send(updates, peer.owner.id)
        if peer.owner == user:
            result_update = updates

    if updates_to_create:
        await Update.bulk_create(updates_to_create)

    return result_update


async def send_messages_channel(
        messages: list[MessageRef], channel: Channel, user: User | None,
) -> Updates | None:
    update_messages = []
    updates_to_create = []

    ucc = UsersChatsChannels()

    async with in_transaction():
        new_pts = await channel.add_pts(len(messages))
        start_pts = new_pts - len(messages)

        for num, message in enumerate(messages, start=1):
            this_pts = start_pts + num
            update_messages.append((message, this_pts))
            ucc.add_message(message.content_id)

            updates_to_create.append(ChannelUpdate(
                channel=channel,
                type=ChannelUpdateType.NEW_MESSAGE,
                related_id=message.id,
                pts=this_pts,
                pts_count=1,
            ))

        await ChannelUpdate.bulk_create(updates_to_create)

    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]

    await SessionManager.send(
        UpdatesWithDefaults(
            updates=[
                UpdateNewChannelMessage(
                    message=DumbChannelMessageToFormat(id=message.id),
                    pts=pts,
                    pts_count=1,
                )
                for message, pts in update_messages
            ],
            users=users,
            chats=chats_and_channels,
        ),
        channel_id=channel.id,
    )

    if user is None:
        return None

    return UpdatesWithDefaults(
        updates=[
            UpdateNewChannelMessage(
                message=await message.to_tl(user),
                pts=pts,
                pts_count=1,
            )
            for message, pts in update_messages
        ],
        users=users,
        chats=chats_and_channels,
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
    await Update.filter(
        Q(update_type=UpdateType.NEW_MESSAGE) | Q(update_type=UpdateType.MESSAGE_EDIT),
        related_id__in=all_ids,
    ).delete()
    await Update.bulk_create(updates_to_create)

    return user_new_pts


async def delete_messages_channel(channel: Channel, messages: list[int]) -> tuple[Updates, int]:
    new_pts = await channel.add_pts(len(messages))
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.DELETE_MESSAGES,
        related_id=None,
        extra_data=b"".join([Long.write(message_id) for message_id in messages]),
        pts=new_pts,
        pts_count=len(messages),
    )

    await ChannelUpdate.filter(
        type__in=(ChannelUpdateType.NEW_MESSAGE, ChannelUpdateType.EDIT_MESSAGE),
        channel=channel, related_id__in=messages,
    ).delete()

    updates = UpdatesWithDefaults(
        updates=[
            UpdateDeleteChannelMessages(
                channel_id=channel.make_id(),
                messages=messages,
                pts=new_pts,
                pts_count=len(messages),
            ),
        ],
        chats=[await channel.to_tl()],
    )

    await SessionManager.send(updates, channel_id=channel.id)

    return updates, new_pts


async def edit_message(user: User, messages: dict[Peer, MessageRef]) -> Updates:
    updates_to_create = []
    result_update = None

    ucc = UsersChatsChannels()
    ucc.add_message(next(iter(messages.values())).content_id)
    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]

    for peer, message in messages.items():
        pts = await State.add_pts(peer.owner, 1)

        updates_to_create.append(
            Update(
                user=peer.owner,
                update_type=UpdateType.MESSAGE_EDIT,
                pts=pts,
                related_id=message.id,
            )
        )

        update = UpdatesWithDefaults(
            updates=[
                UpdateEditMessage(
                    message=await message.to_tl(peer.owner),
                    pts=pts,
                    pts_count=1,
                )
            ],
            users=users,
            chats=chats_and_channels,
        )

        if user.id == peer.owner_id:
            result_update = update

        await SessionManager.send(update, peer.owner.id)

    await Update.bulk_create(updates_to_create)
    return result_update


@overload
async def edit_message_channel(user: User, channel: Channel, message: MessageRef) -> Updates:
    ...


@overload
async def edit_message_channel(user: None, channel: Channel, message: MessageRef) -> None:
    ...


async def edit_message_channel(user: User | None, channel: Channel, message: MessageRef) -> Updates | None:
    new_pts = await channel.add_pts(1)
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.EDIT_MESSAGE,
        related_id=message.id,
        pts=new_pts,
        pts_count=1,
    )

    ucc = UsersChatsChannels()
    ucc.add_message(message.content_id)
    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]

    await SessionManager.send(
        UpdatesWithDefaults(
            updates=[
                UpdateEditChannelMessage(
                    message=DumbChannelMessageToFormat(id=message.id),
                    pts=new_pts,
                    pts_count=1,
                ),
            ],
            users=users,
            chats=chats_and_channels,
        ),
        channel_id=channel.id,
    )

    if user is None:
        return None

    return UpdatesWithDefaults(
        updates=[
            UpdateEditChannelMessage(
                message=await message.to_tl(user),
                pts=new_pts,
                pts_count=1,
            ),
        ],
        users=users,
        chats=chats_and_channels,
    )


async def pin_dialog(user: User, peer: Peer, dialog: Dialog) -> None:
    new_pts = await State.add_pts(user, 1)
    await Update.create(
        user=user,
        update_type=UpdateType.DIALOG_PIN,
        pts=new_pts,
        related_id=peer.id,
    )

    ucc = UsersChatsChannels()
    ucc.add_peer(peer)
    ucc.add_user(user.id)
    users, chats, channels = await ucc.resolve()

    updates = UpdatesWithDefaults(
        updates=[
            UpdateDialogPinned(
                pinned=dialog.pinned_index is not None,
                peer=DialogPeer(
                    peer=peer.to_tl(),
                ),
            )
        ],
        users=users,
        chats=[*chats, *channels],
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

    ucc = UsersChatsChannels()
    ucc.add_peer(peer)
    users, chats, channels = await ucc.resolve()

    updates = UpdatesWithDefaults(
        updates=[UpdateDraftMessage(peer=peer.to_tl(), draft=draft)],
        users=users,
        chats=[*chats, *channels],
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

    ucc = UsersChatsChannels()
    for dialog in dialogs:
        ucc.add_peer(dialog.peer)

    users, chats, channels = await ucc.resolve()

    updates = UpdatesWithDefaults(
        updates=[
            UpdatePinnedDialogs(
                order=[
                    DialogPeer(peer=dialog.peer.to_tl())
                    for dialog in dialogs
                ],
            )
        ],
        users=users,
        chats=[*chats, *channels],
    )

    await SessionManager.send(updates, user.id)


async def pin_message(user: User, messages: dict[Peer, MessageRef]) -> Updates:
    updates_to_create = []
    result_update = None

    ucc = UsersChatsChannels()
    ucc.add_message(next(iter(messages.values())).content_id)
    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]

    for peer, message in messages.items():
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
            users=users,
            chats=chats_and_channels,
        )

        if user.id == peer.owner.id:
            result_update = update

        await SessionManager.send(update, peer.owner.id)

    await Update.bulk_create(updates_to_create)
    return result_update


async def update_user(user: User) -> None:
    updates_to_create = []

    user_tl = await user.to_tl()

    peer: Peer
    # TODO: probably dont do THIS
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
            users=[user_tl],
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
    users_tl = await User.to_tl_bulk(await User.filter(id__in=participant_ids))
    chat_tl = await chat.to_tl()

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
            users=users_tl,
            chats=[chat_tl],
        )

        await SessionManager.send(updates, peer.owner.id)
        if peer.owner == user:
            result_update = updates

    await Update.bulk_create(updates_to_create)
    return result_update


async def update_status(user: User, status: Presence, peers: list[Peer | User]) -> None:
    user_tl = await user.to_tl()

    for peer in peers:
        peer_user = peer.owner if isinstance(peer, Peer) else peer
        updates = UpdatesWithDefaults(
            updates=[
                UpdateUserStatus(
                    user_id=user.id,
                    status=await status.to_tl(peer_user),
                ),
            ],
            users=[user_tl],
        )

        await SessionManager.send(updates, peer_user.id)


async def update_user_name(user: User) -> None:
    updates_to_create = []

    username = await user.get_username()
    username = username.username if username is not None else None

    user_tl = await user.to_tl()

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
            users=[user_tl],
        ), peer.owner.id)

    await Update.bulk_create(updates_to_create)


async def add_remove_contact(user: User, targets: list[User]) -> Updates:
    updates = []
    users = []
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
        users.append(target)

    updates = UpdatesWithDefaults(
        updates=updates,
        users=await User.to_tl_bulk(users),
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
        users=[await target.user.to_tl()],
    ), user.id)


async def update_chat(chat: Chat, user: User | None = None) -> Updates | None:
    updates_to_create = []
    update_to_return = None

    chat_tl = await chat.to_tl()

    peer: Peer
    async for peer in Peer.filter(chat=chat).select_related("owner"):
        pts = await State.add_pts(peer.owner, 1)
        updates_to_create.append(Update(
            user=peer.owner, update_type=UpdateType.UPDATE_CHAT, pts=pts, related_id=chat.id,
        ))

        updates = UpdatesWithDefaults(
            updates=[UpdateChat(chat_id=chat.make_id())],
            chats=[chat_tl],
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

    ucc = UsersChatsChannels()
    ucc.add_peer(dialog.peer)
    users, chats, channels = await ucc.resolve()

    await SessionManager.send(UpdatesWithDefaults(
        updates=[
            UpdateDialogUnreadMark(
                peer=DialogPeer(peer=dialog.peer.to_tl()),
                unread=dialog.unread_mark,
            ),
        ],
        users=users,
        chats=[*chats, *channels],
    ), user.id)


async def update_read_history_inbox(peer: Peer, max_id: int, unread_count: int) -> tuple[int, Updates]:
    pts = await State.add_pts(peer.owner, 1)
    await Update.create(
        user=peer.owner, update_type=UpdateType.READ_INBOX, pts=pts, pts_count=1, related_id=peer.id,
        additional_data=[max_id, unread_count],
    )

    ucc = UsersChatsChannels()
    ucc.add_peer(peer)
    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]

    updates = UpdatesWithDefaults(
        updates=[
            UpdateReadHistoryInbox(
                peer=peer.to_tl(),
                max_id=max_id,
                still_unread_count=unread_count,
                pts=pts,
                pts_count=1,
            ),
        ],
        users=users,
        chats=chats_and_channels,
    )

    await SessionManager.send(updates, peer.owner.id)

    return pts, updates


async def update_read_history_inbox_channel(user: User, channel_id: int, max_id: int, unread_count: int) -> Updates:
    pts = await State.add_pts(user, 1)
    await Update.create(
        user=user, update_type=UpdateType.READ_INBOX_CHANNEL, pts=pts, pts_count=1, related_id=channel_id,
        additional_data=[max_id, unread_count],
    )

    ucc = UsersChatsChannels()
    ucc.add_channel(channel_id)
    users, chats, channels = await ucc.resolve()
    chats_and_channels = [*chats, *channels]

    updates = UpdatesWithDefaults(
        updates=[
            UpdateReadChannelInbox(
                channel_id=Channel.make_id_from(channel_id),
                max_id=max_id,
                still_unread_count=unread_count,
                pts=pts,
            ),
        ],
        users=users,
        chats=chats_and_channels,
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_read_history_outbox_channel(channel: Channel, max_ids: dict[User, int]) -> None:
    updates_to_create = []

    channels = [await channel.to_tl()]

    for user, max_id in max_ids.items():
        pts = await State.add_pts(user, 1)
        updates_to_create.append(Update(
            user=user, update_type=UpdateType.READ_OUTBOX_CHANNEL, pts=pts, pts_count=1, related_id=channel.id,
            additional_data=[max_id],
        ))

        updates = UpdatesWithDefaults(
            updates=[
                UpdateReadChannelOutbox(
                    channel_id=channel.make_id(),
                    max_id=max_id,
                ),
            ],
            users=[],
            chats=channels,
        )

        await SessionManager.send(updates, user.id)

    if updates_to_create:
        await Update.bulk_create(updates_to_create)


async def update_read_history_outbox(messages: dict[Peer, int]) -> None:
    updates_to_create = []

    # TODO: resolve related users/chats/channels here, before loop
    #  (if peer is USER, then related users is [peer.user], and so on)

    for peer, max_id in messages.items():
        pts = await State.add_pts(peer.owner, 1)
        updates_to_create.append(Update(
            user=peer.owner, update_type=UpdateType.READ_OUTBOX, pts=pts, pts_count=1, related_id=peer.id,
            additional_data=[max_id],
        ))

        ucc = UsersChatsChannels()
        ucc.add_peer(peer)
        # TODO: move this out of the loop
        users, chats, channels = await ucc.resolve()

        await SessionManager.send(UpdatesWithDefaults(
            updates=[
                UpdateReadHistoryOutbox(
                    peer=peer.to_tl(),
                    max_id=max_id,
                    pts=pts,
                    pts_count=1,
                ),
            ],
            users=users,
            chats=[*chats, *channels],
        ), peer.owner.id)

    await Update.bulk_create(updates_to_create)


@overload
async def update_channel(channel: Channel, user: User, send_to_users: list[int] | None = None) -> Updates:
    ...


@overload
async def update_channel(channel: Channel, user: None = None, send_to_users: list[int] | None = None) -> None:
    ...


async def update_channel(
        channel: Channel, user: User | None = None, send_to_users: list[int] | None = None,
) -> Updates | None:
    new_pts = await channel.add_pts(1)
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.UPDATE_CHANNEL,
        related_id=None,
        pts=new_pts,
        pts_count=1,
    )

    await SessionManager.send(
        UpdatesWithDefaults(
            updates=[UpdateChannel(channel_id=channel.make_id())],
            chats=[await channel.to_tl()],
        ),
        channel_id=channel.id if send_to_users is None else None,
        user_id=send_to_users,
    )

    if user is not None:
        return UpdatesWithDefaults(
            updates=[UpdateChannel(channel_id=channel.make_id())],
            chats=[await channel.to_tl()],
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

    ucc = UsersChatsChannels()

    for dialog in dialogs:
        folder_peers.append(FolderPeer(peer=dialog.peer.to_tl(), folder_id=dialog.folder_id.value))
        ucc.add_peer(dialog.peer)

    users, chats, channels = await ucc.resolve()

    updates = UpdatesWithDefaults(
        updates=[
            UpdateFolderPeers(
                folder_peers=folder_peers,
                pts=new_pts,
                pts_count=len(dialogs),
            )
        ],
        users=users,
        chats=[*chats, *channels],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_chat_default_banned_rights(chat: Chat, user: User | None = None) -> Updates | None:
    updates_to_create = []
    update_to_return = None

    banned_rights = chat.banned_rights.to_tl()

    chat_tl = await chat.to_tl()

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
            chats=[chat_tl],
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
        chats=[await channel.to_tl()],
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
                poll=poll.to_tl(),
                results=await poll.to_tl_results(),
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


async def update_reactions(user: User, messages: list[MessageRef], peer: Peer, send: bool = True) -> Updates:
    ucc = UsersChatsChannels()

    # TODO: add reactions and not messages maybe?
    for message in messages:
        ucc.add_message(message.content_id)

    users, chats, channels = await ucc.resolve()

    updates = UpdatesWithDefaults(
        updates=[
            UpdateMessageReactions(
                peer=peer.to_tl(),
                msg_id=message.id,
                reactions=await message.content.to_tl_reactions(user),
            ) for message in messages
        ],
        users=users,
        chats=[*chats, *channels],
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

    await SessionManager.send(
        UpdatesWithDefaults(
            updates=[
                UpdateEncryption(
                    chat=chat.to_tl(),
                    date=int(update.date.timestamp()),
                ),
            ],
            users=[await other_user.to_tl()],
        ),
        user_id=user.id,
    )


async def send_encrypted_update(update: SecretUpdate) -> None:
    logger.trace(
        f"Sending secret update of type {update.type!r} "
        f"to user {update.authorization.user_id} (auth {update.authorization.id})"
    )
    await SessionManager.send(
        UpdatesWithDefaults(updates=[update.to_tl()]),
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

    unconfirmed = not auth.confirmed
    updates = UpdatesWithDefaults(
        updates=[
            UpdateNewAuthorization(
                unconfirmed=unconfirmed,
                hash=auth.tl_hash,
                date=int(auth.created_at.timestamp()) if unconfirmed else None,
                device=auth.device_model if unconfirmed else None,
                location=auth.ip if unconfirmed else None,
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
        user.id,
        min_layer=163,
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

    updates = UpdatesWithDefaults(updates=[UpdateStickerSets()])

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
                wallpaper=chat_wallpaper.wallpaper.to_tl() if chat_wallpaper is not None else None,
            )
        ],
        users=[await target.to_tl()]
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


async def read_channel_messages_contents(user: User, channel: Channel, message_ids: list[int]) -> None:
    # TODO: do we save it in database?
    #  if yes - what pts sequence do we even use?
    #  if no - that's stupid, no?
    #  await Update.create(
    #      user=user,
    #      update_type=UpdateType.READ_CHANNEL_MESSAGES_CONTENTS,
    #      pts=new_pts,
    #      pts_count=pts_count,
    #      related_id=channel.id,
    #      related_ids=message_ids,
    #  )

    await SessionManager.send(
        UpdatesWithDefaults(
            updates=[
                UpdateChannelReadMessagesContents(
                    messages=message_ids,
                    channel_id=channel.id,
                )
            ],
        ),
        user.id
    )


async def new_scheduled_message(user: User, message: MessageRef) -> Updates:
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


async def migrate_chat(chat: Chat, channel: Channel, user: User | None = None) -> Updates | None:
    updates_to_create = []
    update_to_return = None

    chats_and_channels = [await chat.to_tl(), await channel.to_tl()]

    peer: Peer
    async for peer in Peer.filter(chat=chat).select_related("owner"):
        pts = await State.add_pts(peer.owner, 2)
        updates_to_create.append(Update(
            user=peer.owner, update_type=UpdateType.UPDATE_CHAT, pts=pts - 1, related_id=chat.id
        ))
        updates_to_create.append(Update(
            user=peer.owner, update_type=UpdateType.UPDATE_CHANNEL, pts=pts, related_id=channel.id
        ))

        updates = UpdatesWithDefaults(
            updates=[
                UpdateChat(chat_id=chat.make_id()),
                UpdateChannel(channel_id=channel.make_id())
            ],
            chats=chats_and_channels,
        )
        if user == peer.owner:
            update_to_return = updates

        await SessionManager.send(updates, peer.owner.id)

    await Update.bulk_create(updates_to_create)

    return update_to_return


async def bot_callback_query(bot: User, query: CallbackQuery) -> None:
    new_pts = await State.add_pts(bot, 1)

    await Update.create(
        user=bot,
        update_type=UpdateType.BOT_CALLBACK_QUERY,
        pts=new_pts,
        pts_count=1,
        related_id=query.id,
        related_ids=[],
    )

    ucc = UsersChatsChannels()
    ucc.add_message(query.message.content_id)
    users, chats, channels = await ucc.resolve()

    updates = UpdatesWithDefaults(
        updates=[
            UpdateBotCallbackQuery(
                query_id=query.id,
                user_id=query.user_id,
                peer=query.message.peer.to_tl(),
                msg_id=query.message_id,
                chat_instance=0,
                data=query.data,
            )
        ],
        users=users,
        chats=[*chats, *channels],
    )

    await SessionManager.send(updates, bot.id)


async def update_user_phone(user: User) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_PHONE,
        pts=new_pts,
        pts_count=1,
        related_id=user.id,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateUserPhone(
                user_id=user.id,
                phone=user.phone_number,
            )
        ],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_peer_notify_settings(
        user: User, peer: Peer | None, not_peer: NotifySettingsNotPeerType | None, settings: PeerNotifySettings,
) -> Updates:
    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_PEER_NOTIFY_SETTINGS,
        pts=await State.add_pts(user, 1),
        pts_count=1,
        related_id=peer.id if peer is not None else None,
        additional_data=[not_peer.value] if not_peer else None,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateNotifySettings(
                peer=PeerNotifySettings.peer_to_tl(peer, not_peer),
                notify_settings=settings.to_tl(),
            )
        ],
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_saved_gifs(user: User) -> Updates:
    await Update.create(
        user=user,
        update_type=UpdateType.SAVED_GIFS,
        pts=await State.add_pts(user, 1),
        pts_count=1,
        related_id=None,
    )

    updates = UpdatesWithDefaults(updates=[UpdateSavedGifs()])

    await SessionManager.send(updates, user.id)

    return updates


async def bot_inline_query(bot: User, query: InlineQuery) -> None:
    new_pts = await State.add_pts(bot, 1)

    await Update.create(
        user=bot,
        update_type=UpdateType.BOT_INLINE_QUERY,
        pts=new_pts,
        pts_count=1,
        related_id=query.id,
        related_ids=[],
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdateBotInlineQuery(
                query_id=query.id,
                user_id=query.user_id,
                query=query.query,
                peer_type=InlineQuery.INLINE_PEER_TO_TL[query.inline_peer],
                offset=query.offset,
            )
        ],
        users=[await query.user.to_tl()],
    )

    await SessionManager.send(updates, bot.id)


async def update_recent_stickers(user: User) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_RECENT_STICKERS,
        pts=new_pts,
        pts_count=1,
        related_id=None,
    )

    updates = UpdatesWithDefaults(updates=[UpdateRecentStickers()])

    await SessionManager.send(updates, user.id)

    return updates


async def update_faved_stickers(user: User) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_FAVED_STICKERS,
        pts=new_pts,
        pts_count=1,
        related_id=None,
    )

    updates = UpdatesWithDefaults(updates=[UpdateFavedStickers()])

    await SessionManager.send(updates, user.id)

    return updates


async def pin_saved_dialog(user: User, dialog: SavedDialog) -> None:
    new_pts = await State.add_pts(user, 1)
    await Update.create(
        user=user,
        update_type=UpdateType.SAVED_DIALOG_PIN,
        pts=new_pts,
        related_id=dialog.peer_id,
    )

    ucc = UsersChatsChannels()
    ucc.add_peer(dialog.peer)
    ucc.add_user(user.id)
    users, chats, channels = await ucc.resolve()

    updates = UpdatesWithDefaults(
        updates=[
            UpdateSavedDialogPinned(
                pinned=dialog.pinned_index is not None,
                peer=DialogPeer(peer=dialog.peer.to_tl()),
            ),
        ],
        users=users,
        chats=[*chats, *channels],
    )

    await SessionManager.send(updates, user.id)


async def reorder_pinned_saved_dialogs(user: User, dialogs: list[SavedDialog]) -> None:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.SAVED_DIALOG_PIN_REORDER,
        pts=new_pts,
        related_id=None,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdatePinnedSavedDialogs(
                order=[
                    DialogPeer(peer=dialog.peer.to_tl())
                    for dialog in dialogs
                ],
            )
        ],
        users=[
            await user.to_tl(),
            *await User.to_tl_bulk([dialog.peer.user for dialog in dialogs if dialog.peer.type is PeerType.USER]),
        ],
        # TODO: chats and channels
        chats=[],
    )

    await SessionManager.send(updates, user.id)


async def update_privacy(user: User, rule: PrivacyRule, rules: PrivacyRules) -> Updates:
    new_pts = await State.add_pts(user, 1)

    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_PRIVACY,
        pts=new_pts,
        pts_count=1,
        related_id=rule.id,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdatePrivacy(
                key=rule.key.to_tl(),
                rules=rules.rules,
            ),
        ],
        users=rules.users,
        chats=rules.chats,
    )

    await SessionManager.send(updates, user.id)

    return updates


async def update_channel_available_messages(channel: Channel, min_id: int) -> Updates | None:
    await ChannelUpdate.create(
        channel=channel,
        type=ChannelUpdateType.UPDATE_MIN_AVAILABLE_ID,
        related_id=None,
        pts=await channel.add_pts(1),
        pts_count=1,
        extra_data=Long.write(min_id),
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateChannelAvailableMessages(
            channel_id=channel.make_id(),
            available_min_id=min_id,
        )],
        chats=[await channel.to_tl()],
    )

    await SessionManager.send(updates, channel_id=channel.id)

    return updates


async def update_channel_participant_available_message(user: User, channel: Channel, min_id: int) -> Updates:
    await Update.create(
        user=user,
        update_type=UpdateType.UPDATE_CHANNEL_MIN_AVAILABLE_ID,
        pts=await State.add_pts(user, 1),
        pts_count=1,
        related_id=channel.id,
        additional_data=[min_id],
    )

    updates = UpdatesWithDefaults(
        updates=[UpdateChannelAvailableMessages(
            channel_id=channel.make_id(),
            available_min_id=min_id,
        )],
        chats=[await channel.to_tl()],
    )

    await SessionManager.send(updates, user_id=user.id)

    return updates


async def phone_call_update(user: User, call: PhoneCall, sessions: list[int] | None = None) -> Updates:
    new_pts = await State.add_pts(user, 1)
    await Update.create(
        user=user,
        update_type=UpdateType.PHONE_CALL,
        pts=new_pts,
        pts_count=1,
        related_id=call.id,
    )

    updates = UpdatesWithDefaults(
        updates=[
            UpdatePhoneCall(
                phone_call=call.to_tl(),
            ),
        ],
        users=[
            await call.from_user.to_tl(),
            await call.to_user.to_tl(),
        ],
    )

    await SessionManager.send(
        updates,
        user_id=user.id if sessions is not None else None,
        auth_id=sessions,
    )

    return updates


async def phone_signaling_update(session_id: int, call_id: int, data: bytes) -> None:
    await SessionManager.send(
        UpdatesWithDefaults(
            updates=[
                UpdatePhoneCallSignalingData(
                    phone_call_id=call_id,
                    data=data,
                ),
            ],
        ),
        auth_id=[session_id],
    )
