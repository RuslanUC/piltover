from time import time
from typing import TypeVar, Generic

from piltover.context import request_ctx, RequestContext
from piltover.db.enums import ChatType
from piltover.db.models import User, Chat, Message, State
from piltover.session_manager import SessionManager
from piltover.tl import TLObject, Updates, \
    UpdateShortSentMessage, UpdateShortMessage, UpdateNewMessage, UpdateMessageID, UpdateReadHistoryInbox, \
    UpdateDeleteMessages
from piltover.tl.functions.messages import SendMessage
from piltover.utils.utils import SingletonMeta

T = TypeVar("T")


class UpdatesContext(Generic[T]):
    def __init__(self, context: T, exclude: list[User | int]):
        self.context = context
        self.exclude: list[int] = [excl.id if isinstance(excl, User) else excl for excl in exclude]


# TODO: this NEEDS to be rewritten
class UpdatesManager(metaclass=SingletonMeta):
    async def _send_updates_chat_nowrite(
            self, ctx: UpdatesContext[Chat], *updates: TLObject, update_users: list[User], date: int, **kwargs
    ):
        chat = ctx.context
        users = []
        if chat.type in {ChatType.SAVED, ChatType.PRIVATE}:
            users = await User.filter(dialogs__chat=chat, id__not_in=ctx.exclude)

        updates_ = Updates(
            updates=[],
            users=[],
            chats=[],
            date=date,
            seq=0,
        )

        for user in users:
            updates_.updates = list(updates)
            updates_.users = [await upd_user.to_tl(user) for upd_user in update_users]

            await SessionManager().send(updates_, user.id, **kwargs)

    @staticmethod
    async def _send_message_chat(chat: Chat, message: Message, exclude_ids: list[int]) -> None:
        users = await User.filter(dialogs__chat=chat)
        for user in users:
            if user.id in exclude_ids:
                continue
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

    async def send_message(self, user: User, message: Message, has_media: bool = False) -> (Updates |
                                                                                            UpdateShortSentMessage):
        """
        Sends a newly-created message to the users from message chat.
        Returns update object that should be sent as response to `sendMessage` request.
        """

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

    async def delete_messages(self, user: User, chats: list[Chat], message_ids: dict[int, list[int]]) -> int:
        for chat in chats:
            # TODO
            #for update_user in await User.filter(dialogs__chat=chat, id__not_in=user.id):
            #    await UpdateV2.bulk_create([
            #        UpdateV2(type=UpdateType.MESSAGE_DELETE, related_id=message_id, user=chat)
            #        for message_id in message_ids[chat.id]
            #    ])

            upd = UpdateDeleteMessages(messages=message_ids[chat.id], pts=0, pts_count=len(message_ids[chat.id]))
            await self._send_updates_chat_nowrite(UpdatesContext(chat, [user]), upd, update_users=[], date=int(time()))

        all_ids = [i for ids in message_ids.values() for i in ids]
        new_pts = await State.add_pts(user, len(all_ids))

        self_upd = UpdateDeleteMessages(messages=all_ids, pts=new_pts, pts_count=len(all_ids))
        updates = Updates(updates=[self_upd], users=[], chats=[], date=int(time()), seq=0)
        await SessionManager().send(updates, user.id)

        return new_pts
