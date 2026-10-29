from datetime import datetime, UTC, timedelta

from tortoise import Model, fields

from piltover.app.utils.utils import telegram_hash
from piltover.db import models
from piltover.tl import WebPage, WebPageEmpty, WebPagePending
from piltover.tl.base import WebPage as TLWebPageBase


class WebpageMetadata(Model):
    id: int = fields.BigIntField(primary_key=True)
    url: str = fields.CharField(max_length=512)
    created_at: datetime = fields.DateTimeField(auto_now_add=True)
    pending: bool = fields.BooleanField(default=True)
    title: str | None = fields.CharField(max_length=128, null=True, default=None)
    site_name: str | None = fields.CharField(max_length=64, null=True, default=None)
    description: str | None = fields.CharField(max_length=512, null=True, default=None)
    image: models.File = fields.ForeignKeyField("models.File", null=True, default=None)

    class Meta:
        indexes = (
            ("url", "created_at"),
        )

    def to_tl(self) -> WebPage | WebPageEmpty | WebPagePending:
        if self.pending and (datetime.now(UTC) - self.created_at) < timedelta(seconds=30):
            return WebPagePending(
                id=self.id,
                url=self.url,
                # docs say that this is creation timestamp, clients treat it like "retry in", so idk
                date=int(self.created_at.timestamp()) + 30,
            )

        if self.title is None:
            return WebPageEmpty(
                id=self.id,
                url=self.url,
            )

        return WebPage(
            id=self.id,
            url=self.url,
            display_url=self.url,
            hash=telegram_hash((self.url, int(self.created_at.timestamp())), 32),
            type_="article",
            site_name=self.site_name[:32],
            title=self.title[:64],
            description=self.description[:192] if self.description else None,
            # TODO: include photo
        )
