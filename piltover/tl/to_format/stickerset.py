from piltover.context import serialization_ctx
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class StickerSetToFormat(types.StickerSetToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

        return LayerConverter.downgrade(
            obj=types.StickerSet(
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
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()
