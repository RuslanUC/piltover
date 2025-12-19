from __future__ import annotations

from tortoise import Model, fields

from piltover.db import models
from piltover.db.enums import InlineQueryResultType
from piltover.tl import BotInlineMessageText, BotInlineMessageMediaAuto, BotInlineResult, BotInlineMediaResult, objects


# TODO: support reply markup in inline results
class InlineQueryResultItem(Model):
    id: int = fields.BigIntField(pk=True)
    result: models.InlineQueryResult = fields.ForeignKeyField("models.InlineQueryResult")
    item_id: str = fields.CharField(max_length=64)
    position: int = fields.SmallIntField()
    type: InlineQueryResultType = fields.CharEnumField(InlineQueryResultType)
    photo: models.File = fields.ForeignKeyField("models.File", null=True, default=None, related_name="inline_photo")
    document: models.File = fields.ForeignKeyField("models.File", null=True, default=None, related_name="inline_document")
    title: str | None = fields.CharField(max_length=128, null=True, default=None)
    description: str | None = fields.CharField(max_length=240, null=True, default=None)
    url: str | None = fields.TextField(null=True, default=None)
    send_message_text: str | None = fields.TextField(null=True, default=None)
    send_message_no_webpage: bool = fields.BooleanField(default=False)
    send_message_invert_media: bool = fields.BooleanField(default=False)
    # TODO: use tl for entities
    send_message_entities: list[dict] | None = fields.JSONField(null=True, default=None)

    result_id: int
    photo_id: int | None
    document_id: int | None

    def to_tl(self) -> BotInlineResult | BotInlineMediaResult:
        entities = []
        for entity in (self.send_message_entities or []):
            tl_id = entity.pop("_")
            entities.append(objects[tl_id](**entity))
            entity["_"] = tl_id

        if self.photo or self.document:
            send_message = BotInlineMessageMediaAuto(
                invert_media=self.send_message_invert_media,
                message=self.send_message_text or "",
                entities=entities,
                reply_markup=None,
            )
        else:
            send_message = BotInlineMessageText(
                no_webpage=self.send_message_no_webpage,
                invert_media=self.send_message_invert_media,
                message=self.send_message_text or "",
                entities=entities,
                reply_markup=None,
            )

        if self.photo:
            return BotInlineMediaResult(
                id=self.item_id,
                type_=self.type.value,
                photo=self.photo.to_tl_photo(),
                send_message=send_message,
            )
        elif self.document:
            return BotInlineMediaResult(
                id=self.item_id,
                type_=self.type.value,
                document=self.document.to_tl_document(),
                title=self.title,
                description=self.description,
                send_message=send_message,
            )
        else:
            return BotInlineResult(
                id=self.item_id,
                type_=self.type.value,
                title=self.title,
                description=self.description,
                url=self.url,
                send_message=send_message,
            )
