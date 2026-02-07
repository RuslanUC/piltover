from piltover.context import serialization_ctx
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class ThemeToFormat(types.ThemeToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()
        return LayerConverter.downgrade(
            obj=types.Theme(
                creator=self.creator_id == ctx.user_id,
                for_chat=self.for_chat,
                id=self.id,
                access_hash=-1,
                slug=self.slug,
                title=self.title,
                document=self.document,
                settings=self.settings,
                emoticon=self.emoticon,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()