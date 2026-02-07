from piltover.context import serialization_ctx
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


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
