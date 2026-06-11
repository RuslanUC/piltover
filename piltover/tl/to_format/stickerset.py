from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class StickerSetToFormat(types.StickerSetToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
        return types.StickerSet(
            id=self.info.id,
            access_hash=self.info.access_hash,
            title=self.info.title,
            short_name=self.info.short_name or "",
            official=self.info.official,
            creator=ctx.user_id == self.info.creator_id,
            installed_date=self.for_user.installed_date,
            archived=self.for_user.archived,
            count=self.info.count,
            hash=self.info.hash,
            masks=self.info.masks,
            emojis=self.info.emoji,

            thumbs=self.info.thumbs,
            thumb_dc_id=2 if self.info.thumbs is not None else None,
            thumb_version=self.info.thumb_version,
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)
