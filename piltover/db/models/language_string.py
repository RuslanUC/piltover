from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl import LangPackStringDeleted, LangPackStringPluralized, LangPackString
from piltover.tl.base import LangPackString as LangPackStringBase


class LanguageString(Model):
    id: int = fields.BigIntField(pk=True)
    language: models.Language = fields.ForeignKeyField("models.Language")
    key: str = fields.CharField(max_length=128)
    deleted: bool = fields.BooleanField(default=False)
    plural: bool = fields.BooleanField(default=False)
    value: str | None = fields.TextField(null=True, default=None)
    zero_value: str | None = fields.TextField(null=True, default=None)
    one_value: str | None = fields.TextField(null=True, default=None)
    two_value: str | None = fields.TextField(null=True, default=None)
    few_value: str | None = fields.TextField(null=True, default=None)
    many_value: str | None = fields.TextField(null=True, default=None)
    version: int = fields.BigIntField()

    class Meta:
        unique_together = (
            ("language", "key"),
        )

    def to_tl(self) -> LangPackStringBase:
        if self.deleted:
            return LangPackStringDeleted(key=self.key)
        if self.plural:
            return LangPackStringPluralized(
                key=self.key,
                other_value=self.value,
                zero_value=self.zero_value,
                one_value=self.one_value,
                two_value=self.two_value,
                few_value=self.few_value,
                many_value=self.many_value,
            )

        return LangPackString(key=self.key, value=self.value)
