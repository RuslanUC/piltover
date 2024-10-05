from time import time
from typing import Any, TypeVar, Generic

from piltover.app.utils.to_tl import ToTL
from piltover.context import request_ctx, RequestContext
from piltover.db.enums import ChatType
from piltover.db.models import User, Update, Chat, Message
from piltover.session_manager import SessionManager
from piltover.tl import TLObject, PeerUser, DialogPeer, NotifyForumTopic, NotifyPeer, Updates, \
    UpdateShortSentMessage, UpdateShortMessage, UpdateNewMessage, UpdateMessageID, UpdateReadHistoryInbox, \
    UpdateDeleteMessages
from piltover.tl.core_types import SerializedObject
from piltover.tl.functions.messages import SendMessage
from piltover.utils.utils import SingletonMeta


def _extract_id(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    elif isinstance(value, PeerUser):
        return value.user_id
    elif isinstance(value, DialogPeer):
        return _extract_id(value.peer)
    elif isinstance(value, (NotifyPeer, NotifyForumTopic)):
        return _extract_id(value.peer)


T = TypeVar("T")


class UpdatesContext(Generic[T]):
    def __init__(self, context: T, exclude: list[User | int]):
        self.context = context
        self.exclude: list[int] = [excl.id if isinstance(excl, User) else excl for excl in exclude]


class FakeUpdate:
    __slots__ = ["update_data"]

    def __init__(self, update_data: bytes):
        self.update_data = update_data


class UpdatesManager(metaclass=SingletonMeta):
    async def write_update(
            self, user: User, obj: TLObject, *, last_update: Update | None = None
    ) -> Update | FakeUpdate:
        if not hasattr(obj, "pts"):
            return FakeUpdate(update_data=obj.write())

        last_update = last_update or await Update.filter(user=user).order_by("-pts").first()
        last_pts = last_update.pts if last_update is not None else 0

        this_pts = last_pts + 1
        if hasattr(obj, "pts_count"):
            this_pts += getattr(obj, "pts_count", 1) - 1
        setattr(obj, "pts", this_pts)

        ids = None
        for attr in ("user_id", "peer", "peer_id"):
            if not hasattr(obj, attr):
                continue
            ids = ids or []

            value = getattr(obj, attr)
            if (user_id := _extract_id(value)) is not None:
                ids.append(user_id)

        return await Update.create(pts=this_pts, update_type=obj.tlid(), update_data=obj.write(),
                                   user_ids_to_fetch=ids, user=user)

    async def write_updates(self, user: User, *objs: TLObject | ToTL) -> list[Update | FakeUpdate]:
        last_real_update = None
        result = []
        for obj in objs:
            if isinstance(obj, ToTL):
                obj = await obj.to_tl(user)
            last_update = await self.write_update(user, obj, last_update=last_real_update)
            result.append(last_update)
            if isinstance(last_update, Update):
                last_real_update = last_update

        return result

    async def _send_updates_chat(
            self, ctx: UpdatesContext[Chat], *updates: TLObject | ToTL, update_users: list[User], date: int, **kwargs
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
            written_updates = await self.write_updates(user, *updates)
            updates_.updates = [SerializedObject(upd.update_data) for upd in written_updates]
            updates_.users = [await upd_user.to_tl(user) for upd_user in update_users]

            await SessionManager().send(updates_, user.id, **kwargs)

    async def send_updates(self, context, *updates: TLObject | ToTL, update_users: list[User], date: int, **kwargs):
        if not isinstance(context, UpdatesContext):
            context = UpdatesContext(context, [])

        if isinstance(context.context, Chat):
            return await self._send_updates_chat(context, *updates, update_users=update_users, date=date, **kwargs)

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
            u_new_msg = ToTL(UpdateNewMessage, ["message"], message=message, pts=0, pts_count=1)
            await self.send_updates(UpdatesContext(chat, [user]), u_new_msg, update_users=[user], date=message.utime())

            u_msg_id = UpdateMessageID(id=message.id, random_id=ctx.obj.random_id)
            u_new_msg = UpdateNewMessage(message=await message.to_tl(user), pts=0, pts_count=1)
            u_read_history = UpdateReadHistoryInbox(peer=await chat.get_peer(user), max_id=message.id,
                                                    still_unread_count=0,
                                                    pts=0, pts_count=1)
            await self.write_updates(user, u_msg_id, u_new_msg, u_read_history)
            updates = Updates(
                updates=[u_msg_id, u_new_msg, u_read_history],
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
                pts=0,
                pts_count=1,
                date=message.utime(),
                reply_to=msg_tl.reply_to,
            )
            await self.write_updates(user, update)
            await SessionManager().send(update, user.id, exclude=[client])
            sent_pts = update.pts

            update.out = False
            update.user_id = user.id
            await self.write_updates(other, update)
            await SessionManager().send(update, other.id)

            return UpdateShortSentMessage(out=True, id=message.id, pts=sent_pts, pts_count=1, date=message.utime())

    async def delete_messages(self, user: User, chats: list[Chat], message_ids: dict[int, list[int]]) -> int:
        for chat in chats:
            upd = UpdateDeleteMessages(messages=message_ids[chat.id], pts=0, pts_count=len(message_ids[chat.id]))
            await self.send_updates(UpdatesContext(chat, [user]), upd, update_users=[], date=int(time()))

        all_ids = [i for ids in message_ids.values() for i in ids]
        self_upd = UpdateDeleteMessages(messages=all_ids, pts=0, pts_count=len(all_ids))
        update = await self.write_update(user, self_upd)
        updates = Updates(
            updates=[self_upd],
            users=[],
            chats=[],
            date=int(time()),
            seq=0,
        )
        await SessionManager().send(updates, user.id)
        return update.pts
