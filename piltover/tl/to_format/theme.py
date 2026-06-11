from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class ThemeToFormat(types.ThemeToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
        return types.Theme(
            creator=self.creator_id == ctx.user_id,
            for_chat=self.for_chat,
            id=self.id,
            access_hash=-1,
            slug=self.slug,
            title=self.title,
            document=self.document,
            settings=self.settings,
            emoticon=self.emoticon,
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)
