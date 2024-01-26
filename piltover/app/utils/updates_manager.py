from piltover.db.models import User, Update
from piltover.tl_new import TLObject
from piltover.utils.utils import SingletonMeta


class UpdatesManager(metaclass=SingletonMeta):
    async def write_update(self, user: User, obj: TLObject, *, last_update: Update | None = None) -> Update:
        last_update = last_update or await Update.filter(user=user).order_by("-pts").first()
        last_pts = last_update.pts if last_update is not None else 0

        this_pts = last_pts + 1
        if hasattr(obj, "pts"):
            setattr(obj, "pts", this_pts)

        return await Update.create(pts=this_pts, update_type=obj.tlid(), update_data=obj.write(), user=user)

    async def write_updates(self, user: User, *objs: TLObject) -> None:
        last_update = None
        for obj in objs:
            last_update = await self.write_update(user, obj, last_update=last_update)
