from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import PollAnswer as TLPollAnswer, TextWithEntities


class PollAnswer(Model):
    id: int = fields.BigIntField(pk=True)
    correct: bool = fields.BooleanField(default=False)
    text: str = fields.CharField(max_length=100)
    option: bytes = fields.BinaryField()
    poll: models.Poll = fields.ForeignKeyField("models.Poll")

    def to_tl(self) -> TLPollAnswer:
        return TLPollAnswer(
            text=TextWithEntities(text=self.text, entities=[]),
            option=self.option,
        )
