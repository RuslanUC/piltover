from piltover.tl import types, UpdateMessageID
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class UpdateMessageIDToFormat(types.UpdateMessageIDToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
        return UpdateMessageID(
            id=self.id,
            random_id=self.random_id if self.target_user == ctx.user_id else 0,
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)
