from __future__ import annotations

from time import time
from typing import cast, Collection

from tortoise import fields, Model
from tortoise.transactions import in_transaction

from piltover.db import models
from piltover.tl.types.updates import State as TLState
from piltover.utils import SingleElementList


class State(Model):
    id: int = fields.BigIntField(primary_key=True)
    pts: int = fields.BigIntField(default=0)
    user: models.User = fields.OneToOneField("models.User")

    user_id: int

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
    async def add_pts(cls, user: models.User | int, pts_count: int) -> int:
        user_id = user.id if isinstance(user, models.User) else user

        if pts_count <= 0:
            return cast(int, await cls.get(user_id=user_id).values_list("pts", flat=True))

        async with in_transaction():
            pts = cast(int, await cls.select_for_update().get(user_id=user_id).values_list("pts", flat=True))
            new_pts = pts + pts_count
            await cls.filter(user_id=user_id).update(pts=new_pts)

        return new_pts

    @classmethod
    async def add_pts_bulk(cls, users: list[models.User], pts_counts: Collection[int] | int) -> list[int]:
        user_ids = [user.id for user in users]

        if not isinstance(pts_counts, Collection):
            pts_counts = SingleElementList(pts_counts, len(users))
        if len(pts_counts) != len(users):
            raise ValueError("\"users\" and \"pts_count\" must have same length")

        async with in_transaction():
            to_update = []
            state_by_user_id = {
                state.user_id: state
                for state in await cls.select_for_update().filter(user_id__in=user_ids).only("id", "user_id", "pts")
            }

            for user_id, pts_count in zip(user_ids, pts_counts):
                if pts_count <= 0:
                    continue
                state = state_by_user_id[user_id]
                state.pts += pts_count
                to_update.append(state)

            if to_update:
                await State.bulk_update(to_update, fields=["pts"])

        return [state_by_user_id[user_id].pts for user_id in user_ids]
