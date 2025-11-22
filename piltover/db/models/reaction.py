from __future__ import annotations

from uuid import UUID

from tortoise import Model, fields
from tortoise.expressions import Q

from piltover.db import models
from piltover.tl import AvailableReaction


class Reaction(Model):
    id: int = fields.BigIntField(pk=True)
    # TortoiseORM does not allow setting collate, so searching by `reaction` works incorrectly
    reaction_id: UUID = fields.UUIDField(index=True)
    reaction: str = fields.CharField(max_length=8)
    title: str = fields.CharField(max_length=64)
    static_icon: models.File = fields.ForeignKeyField("models.File", related_name="static_icon")
    appear_animation: models.File = fields.ForeignKeyField("models.File", related_name="appear_animation")
    select_animation: models.File = fields.ForeignKeyField("models.File", related_name="select_animation")
    activate_animation: models.File = fields.ForeignKeyField("models.File", related_name="activate_animation")
    effect_animation: models.File = fields.ForeignKeyField("models.File", related_name="effect_animation")
    around_animation: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="around_animation")
    center_icon: models.File | None = fields.ForeignKeyField("models.File", null=True, default=None, related_name="center_icon")

    @staticmethod
    def reaction_to_uuid(reaction: str) -> UUID:
        return UUID(bytes=reaction[:4].encode("utf8").ljust(16, b"\x00"))

    @classmethod
    def q_from_reaction(cls, reaction: str) -> Q:
        return Q(reaction_id=cls.reaction_to_uuid(reaction))

    def to_tl_available_reaction(self) -> AvailableReaction:
        return AvailableReaction(
            reaction=self.reaction,
            title=self.title,
            static_icon=self.static_icon.to_tl_document(),
            appear_animation=self.appear_animation.to_tl_document(),
            select_animation=self.select_animation.to_tl_document(),
            activate_animation=self.activate_animation.to_tl_document(),
            effect_animation=self.effect_animation.to_tl_document(),
            around_animation=self.around_animation.to_tl_document() if self.around_animation is not None else None,
            center_icon=self.center_icon.to_tl_document() if self.center_icon is not None else None,
        )
