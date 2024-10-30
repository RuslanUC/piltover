from __future__ import annotations

from time import time

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl.types.updates import State as TLState


class State(Model):
    id: int = fields.BigIntField(pk=True)
    pts: int = fields.BigIntField(default=0)
    #seq: int = fields.BigIntField(default=0)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)

    async def to_tl(self) -> TLState:
        return State(
            pts=self.pts,
            qts=0,
            seq=1,
            date=int(time()),
            unread_count=0,
        )

    @classmethod
    async def add_pts(cls, user: models.User, pts: int, cache_state: bool = True) -> int:
        if hasattr(user, "_cached_updates_state") and cache_state:
            state = getattr(user, "_cached_updates_state")
        else:
            state, _ = await State.get_or_create(user=user)

        state.pts += pts
        await state.save(update_fields=["pts"])
        if cache_state:
            setattr(user, "_cached_updates_state", state)

        return state.pts

    upd = add_pts
