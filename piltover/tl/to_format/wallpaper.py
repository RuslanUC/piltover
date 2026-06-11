from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class WallPaperToFormat(types.WallPaperToFormatInternal):
    __tl_result_id__ = 0xa437c3ed

    def _write(self, ctx: SerializationContext) -> bytes:
        return types.WallPaper(
            id=self.id,
            creator=self.creator_id == ctx.user_id,
            default=False,
            pattern=self.pattern,
            dark=self.dark,
            access_hash=-1,
            slug=self.slug,
            document=self.document,
            settings=self.settings,
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)
