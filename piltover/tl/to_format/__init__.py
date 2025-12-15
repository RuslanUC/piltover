from loguru import logger

from piltover.context import serialization_ctx
from piltover.tl import types, Int, WallPaperToFormatInternal


class WallPaperToFormat(WallPaperToFormatInternal):
    __tl_result_id__ = 0xa437c3ed

    def serialize(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().serialize()

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
        ).serialize()

    def write(self) -> bytes:
        logger.info(f"???")
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            logger.info(f"WHAT??? {ctx!r}")
            return super().write()
        return Int.write(self.__tl_result_id__, False) + self.serialize()
