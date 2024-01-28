from typing import Any, TypeVar, Generic

from piltover.app.utils.to_tl import ToTL
from piltover.db.enums import ChatType
from piltover.db.models import User, Update, Chat
from piltover.session_manager import SessionManager
from piltover.tl_new import TLObject, PeerUser, DialogPeer, NotifyForumTopic, NotifyPeer, Updates
from piltover.tl_new.core_types import SerializedObject
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


class UpdatesManager(metaclass=SingletonMeta):
    async def write_update(self, user: User, obj: TLObject, *, last_update: Update | None = None) -> Update:
        last_update = last_update or await Update.filter(user=user).order_by("-pts").first()
        last_pts = last_update.pts if last_update is not None else 0

        this_pts = last_pts + 1
        if hasattr(obj, "pts"):
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

    async def write_updates(self, user: User, *objs: TLObject | ToTL) -> list[Update]:
        last_update = None
        result = []
        for obj in objs:
            if isinstance(obj, ToTL):
                obj = await obj.to_tl(user)
            last_update = await self.write_update(user, obj, last_update=last_update)
            result.append(last_update)

        return result

    async def _send_updates_chat(self, ctx: UpdatesContext[Chat], *updates: TLObject | ToTL, update_users: list[User], date: int,
                                 **kwargs):
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
