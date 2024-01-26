from __future__ import annotations

from time import time

from tortoise import fields

from piltover.db import models
from piltover.db.models._utils import Model
from piltover.tl_new.types.updates import State as TLState


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
    async def upd(cls, user: models.User, pts: int) -> models.State:
        state, _ = await State.get_or_create(user=user)
        await state.update(pts=state.pts + pts)

        return state
