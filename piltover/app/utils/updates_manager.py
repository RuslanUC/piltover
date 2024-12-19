from time import time
from typing import TypeVar, Generic

from piltover.context import request_ctx, RequestContext
from piltover.db.enums import ChatType, UpdateType
from piltover.db.models import User, Chat, Message, State, UpdateV2
from piltover.session_manager import SessionManager
from piltover.tl import Updates, UpdateShortSentMessage, UpdateShortMessage, UpdateNewMessage, \
    UpdateMessageID, UpdateReadHistoryInbox, UpdateDeleteMessages, UpdateEditMessage
from piltover.tl.functions.messages import SendMessage
from piltover.utils.utils import SingletonMeta

T = TypeVar("T")


class UpdatesContext(Generic[T]):
    def __init__(self, context: T, exclude: list[User | int]):
        self.context = context
        self.exclude: list[int] = [excl.id if isinstance(excl, User) else excl for excl in exclude]


class UpdatesManager(metaclass=SingletonMeta):
    @staticmethod
    async def _send_message_chat(chat: Chat, message: Message, exclude_ids: list[int]) -> None:
        users = await User.filter(dialogs__chat=chat, id__not_in=exclude_ids)
        for user in users:
            updates = Updates(
                updates=[UpdateNewMessage(
                    message=await message.to_tl(user),
                    pts=await State.add_pts(user, 1),
                    pts_count=1,
                )],
                users=[await upd_user.to_tl(user) for upd_user in users],
                chats=[],
                date=message.utime(),
                seq=0,
            )
            await SessionManager().send(updates, user.id)

    async def send_message(
            self, user: User, message: Message, has_media: bool = False
    ) -> Updates | UpdateShortSentMessage:
        ctx: RequestContext[SendMessage] = request_ctx.get()
        client = ctx.client
        chat = message.chat
        if chat.type == ChatType.SAVED or has_media:
            await self._send_message_chat(chat, message, [user.id])

            updates = Updates(
                updates=[
                    UpdateMessageID(
                        id=message.id,
                        random_id=ctx.obj.random_id,
                    ),
                    UpdateNewMessage(
                        message=await message.to_tl(user),
                        pts=await State.add_pts(user, 1),
                        pts_count=1,
                    ),
                    UpdateReadHistoryInbox(
                        peer=await chat.get_peer(user),
                        max_id=message.id,
                        still_unread_count=0,
                        pts=await State.add_pts(user, 1),
                        pts_count=1,
                    )
                ],
                users=[await user.to_tl(user)],
                chats=[],
                date=int(time()),
                seq=0,
            )

            read_history_inbox_args = {
                "update_type": UpdateType.READ_HISTORY_INBOX, "user": user, "related_id": chat.id,
            }
            await UpdateV2.filter(**read_history_inbox_args).delete()
            await UpdateV2.create(**read_history_inbox_args, pts=updates.updates[2].pts, related_ids=[message.id, 0])

            await SessionManager().send(updates, user.id, exclude=[client])
            return updates
        elif chat.type == ChatType.PRIVATE:
            msg_tl = await message.to_tl(user)
            other = await chat.get_other_user(user)

            update = UpdateShortMessage(
                out=True,
                id=message.id,
                user_id=other.id,
                message=message.message,
                pts=await State.add_pts(user, 1),
                pts_count=1,
                date=message.utime(),
                reply_to=msg_tl.reply_to,
            )
            await SessionManager().send(update, user.id, exclude=[client])
            sent_pts = update.pts

            update.out = False
            update.user_id = user.id
            update.pts = await State.add_pts(other, 1)
            await SessionManager().send(update, other.id)

            return UpdateShortSentMessage(out=True, id=message.id, pts=sent_pts, pts_count=1, date=message.utime())

    @staticmethod
    async def delete_messages(user: User, chats: list[Chat], message_ids: dict[int, list[int]]) -> int:
        updates_to_create = []

        for chat in chats:
            for update_user in await User.filter(dialogs__chat=chat, id__not=user.id):
                pts_count = len(message_ids[chat.id])
                pts = await State.add_pts(update_user, pts_count)

                updates_to_create.append(
                    UpdateV2(
                        user=update_user,
                        update_type=UpdateType.MESSAGE_DELETE,
                        pts=pts,
                        related_id=None,
                        related_ids=message_ids[chat.id],
                    )
                )

                await SessionManager().send(
                    Updates(
                        updates=[
                            UpdateDeleteMessages(
                                messages=message_ids[chat.id],
                                pts=pts,
                                pts_count=pts_count
                            )
                        ],
                        users=[],
                        chats=[],
                        date=int(time()),
                        seq=0,
                    ),
                    update_user.id
                )

        all_ids = [i for ids in message_ids.values() for i in ids]
        new_pts = await State.add_pts(user, len(all_ids))
        updates_to_create.append(
            UpdateV2(
                user=user,
                update_type=UpdateType.MESSAGE_DELETE,
                pts=new_pts,
                related_id=None,
                related_ids=all_ids,
            )
        )

        await UpdateV2.filter(related_id__in=all_ids).delete()
        await UpdateV2.bulk_create(updates_to_create)

        self_upd = UpdateDeleteMessages(messages=all_ids, pts=new_pts, pts_count=len(all_ids))
        updates = Updates(updates=[self_upd], users=[], chats=[], date=int(time()), seq=0)
        await SessionManager().send(updates, user.id)

        return new_pts

    @staticmethod
    async def edit_message(message: Message) -> Updates:
        updates_to_create = []
        result_update = None

        for update_user in await User.filter(dialogs__chat=message.chat, id__not_in=message.author.id):
            pts = await State.add_pts(update_user, 1)

            updates_to_create.append(
                UpdateV2(
                    user=update_user,
                    update_type=UpdateType.MESSAGE_EDIT,
                    pts=pts,
                    related_id=message.id,
                )
            )

            update = Updates(
                updates=[
                    UpdateEditMessage(
                        message=await message.to_tl(update_user),
                        pts=pts,
                        pts_count=1,
                    )
                ],
                users=[await message.author.to_tl(update_user)],
                chats=[],
                date=int(time()),
                seq=0,
            )
            if update_user.id == message.author.id:
                result_update = update

            await SessionManager().send(update, update_user.id)

        await UpdateV2.bulk_create(updates_to_create)
        return result_update
