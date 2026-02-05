from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import PollAnswer as TLPollAnswer, TextWithEntities, objects


class PollAnswer(Model):
    id: int = fields.BigIntField(pk=True)
    correct: bool = fields.BooleanField(default=False)
    text: str = fields.CharField(max_length=100)
    entities: list | None = fields.JSONField()
    option: bytes = fields.BinaryField()
    poll: models.Poll = fields.ForeignKeyField("models.Poll")

    def to_tl(self) -> TLPollAnswer:
        entities = []
        for entity in (self.entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))
            entity["_"] = tl_id

        return TLPollAnswer(
            text=TextWithEntities(text=self.text, entities=entities),
            option=self.option,
        )
