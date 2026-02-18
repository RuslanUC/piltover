from __future__ import annotations

from time import time
from typing import cast

from tortoise import fields, Model
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.tl.types.updates import State as TLState


class State(Model):
    id: int = fields.BigIntField(pk=True)
    pts: int = fields.BigIntField(default=0)
    user: models.User = fields.OneToOneField("models.User")

    async def to_tl(self) -> TLState:
        return State(
            pts=self.pts,
            qts=0,
            seq=0,
            date=int(time()),
            unread_count=0,
        )

    # TODO: add add_pts_bulk

    @classmethod
    async def add_pts(cls, user: models.User, pts_count: int) -> int:
        if pts_count <= 0:
            return cast(int, await cls.get(user=user).values_list("pts", flat=True))

        async with in_transaction():
            pts = cast(int, await cls.select_for_update().get(user=user).values_list("pts", flat=True))
            new_pts = pts + pts_count
            await cls.filter(user=user).update(pts=new_pts)

        return new_pts
