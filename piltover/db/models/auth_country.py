from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types.help import Country


class AuthCountry(Model):
    id: int = fields.BigIntField(pk=True)
    iso2: str = fields.CharField(max_length=8, unique=True)
    name: str = fields.CharField(max_length=128)
    hidden: bool = fields.BooleanField(default=False)

    _country_codes_cached = None

    async def to_tl(self) -> Country:
        if self._country_codes_cached is None:
            self._country_codes_cached = await models.AuthCountryCode.filter(country=self).order_by("id")

        return Country(
            iso2=self.iso2,
            default_name=self.name,
            country_codes=[code.to_tl() for code in self._country_codes_cached],
            hidden=self.hidden,
        )

    async def get_internal_hash(self) -> int:
        if self._country_codes_cached is None:
            self._country_codes_cached = await models.AuthCountryCode.filter(country=self).order_by("id")

        int_hash = self.id
        for code in self._country_codes_cached:
            int_hash ^= int_hash >> 21
            int_hash ^= int_hash << 35
            int_hash ^= int_hash >> 4
            int_hash += code.id

        return int_hash
