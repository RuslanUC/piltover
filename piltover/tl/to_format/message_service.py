from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class MessageServiceToFormat(types.MessageServiceToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
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
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)
