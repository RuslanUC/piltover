from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import AvailableReaction


class Reaction(Model):
    id: int = fields.BigIntField(pk=True)
    reaction: str = fields.CharField(max_length=8, index=True)
    title: str = fields.CharField(max_length=64)
    static_icon: models.File = fields.ForeignKeyField("models.File", related_name="static_icon")
    appear_animation: models.File = fields.ForeignKeyField("models.File", related_name="appear_animation")
    select_animation: models.File = fields.ForeignKeyField("models.File", related_name="select_animation")
    activate_animation: models.File = fields.ForeignKeyField("models.File", related_name="activate_animation")
    effect_animation: models.File = fields.ForeignKeyField("models.File", related_name="effect_animation")
    around_animation: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="around_animation")
    center_icon: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="center_icon")

    async def to_tl_available_reaction(self, user: models.User) -> AvailableReaction:
        return AvailableReaction(
            reaction=self.reaction,
            title=self.title,
            static_icon=await self.static_icon.to_tl_document(user),
            appear_animation=await self.appear_animation.to_tl_document(user),
            select_animation=await self.select_animation.to_tl_document(user),
            activate_animation=await self.activate_animation.to_tl_document(user),
            effect_animation=await self.effect_animation.to_tl_document(user),
            around_animation=await self.around_animation.to_tl_document(user) if self.around_animation is not None else None,
            center_icon=await self.center_icon.to_tl_document(user) if self.center_icon is not None else None,
        )
