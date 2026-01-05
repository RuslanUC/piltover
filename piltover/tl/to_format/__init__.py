from piltover.context import serialization_ctx
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types, Int


class WallPaperToFormat(types.WallPaperToFormatInternal):
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
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return Int.write(self.__tl_result_id__, False) + self.serialize()


class MessageServiceToFormat(types.MessageServiceToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()
        return LayerConverter.downgrade(
            obj=types.MessageService(
                id=self.id,
                peer_id=self.peer_id,
                date=self.date,
                action=self.action,
                out=self.author_id == ctx.user_id,
                reply_to=self.reply_to,
                from_id=self.from_id,
                mentioned=False,
                media_unread=False,
                ttl_period=self.ttl_period,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()


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
