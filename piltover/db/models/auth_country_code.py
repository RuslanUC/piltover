from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types.help import CountryCode


class AuthCountryCode(Model):
    id: int = fields.BigIntField(pk=True)
    country: models.AuthCountry = fields.ForeignKeyField("models.AuthCountry")
    code: str = fields.CharField(max_length=4, index=True)
    prefixes: list[str] | None = fields.JSONField(null=True, default=None)
    patterns: list[str] | None = fields.JSONField(null=True, default=None)

    country_id: int

    class Meta:
        unique_together = (
            ("country", "code"),
        )

    def to_tl(self) -> CountryCode:
        return CountryCode(
            country_code=self.code,
            prefixes=self.prefixes,
            patterns=self.patterns,
        )
