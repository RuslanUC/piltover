from __future__ import annotations

from datetime import datetime

from tortoise import Model, fields

from piltover.db import models
from piltover.tl.types.messages import BotResults


class InlineQueryResult(Model):
    id: int = fields.BigIntField(pk=True)
    query: models.InlineQuery = fields.OneToOneField("models.InlineQuery")
    next_offset: str | None = fields.CharField(max_length=96, null=True, default=None)
    cache_time: int = fields.IntField(default=60)
    cache_until: datetime = fields.DatetimeField()
    gallery: bool = fields.BooleanField()
    private: bool = fields.BooleanField()

    query_id: int

    async def get_items(self) -> list[models.InlineQueryResultItem]:
        return await models.InlineQueryResultItem.filter(result=self).order_by("position").select_related(
            "photo", "document", "document__stickerset"
        )

    async def to_tl(self, items: list[models.InlineQueryResultItem] | None = None) -> BotResults:
        if items is None:
            items = await self.get_items()

        return BotResults(
            query_id=self.query_id,
            results=[item.to_tl() for item in items],
            cache_time=self.cache_time,
            users=[],
            gallery=self.gallery,
            next_offset=self.next_offset,
            switch_pm=None,  # TODO: implement switch_pm
            switch_webview=None,
        )

