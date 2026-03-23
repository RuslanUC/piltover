from piltover.context import serialization_ctx, NeedContextValuesContext
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class StickerSetToFormat(types.StickerSetToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

        if ctx.values is None or self.id not in ctx.values.stickersets:
            installed_date = None
            archived = False
        else:
            installed = ctx.values.stickersets[self.id]
            installed_date = int(installed.installed_at.timestamp())
            archived = installed.archived

        return LayerConverter.downgrade(
            obj=types.StickerSet(
                id=self.id,
                access_hash=self.access_hash,
                title=self.title,
                short_name=self.short_name,
                official=self.official,
                creator=ctx.user_id == self.creator_id,
                installed_date=installed_date,
                archived=archived,
                count=self.count,
                hash=self.hash,
                masks=self.masks,
                emojis=self.emoji,

                thumbs=self.thumbs,
                thumb_dc_id=2 if self.thumbs is not None else None,
                thumb_version=self.thumb_version,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.stickersets.add(self.id)
