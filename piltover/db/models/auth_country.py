from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types.help import Country


class AuthCountry(Model):
    id: int = fields.BigIntField(pk=True)
    iso2: str = fields.CharField(max_length=8, unique=True)
    name: str = fields.CharField(max_length=128)
    hidden: bool = fields.BooleanField(default=False)

    authcountrycodes: fields.ReverseRelation[models.AuthCountryCode]

    def to_tl(self) -> Country:
        if not self.authcountrycodes._fetched:
            raise RuntimeError("Auth country codes must be prefetched")

        return Country(
            iso2=self.iso2,
            default_name=self.name,
            country_codes=[code.to_tl() for code in self.authcountrycodes],
            hidden=self.hidden,
        )

    def get_internal_hash(self) -> int:
        if not self.authcountrycodes._fetched:
            raise RuntimeError("Auth country codes must be prefetched")

        int_hash = self.id
        for code in self.authcountrycodes:
            int_hash ^= int_hash >> 21
            int_hash ^= int_hash << 35
            int_hash ^= int_hash >> 4
            int_hash += code.id

        return int_hash
