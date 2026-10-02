from piltover.tl import types, LongVector
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class LongVectorToFormat(types.internal.LongVectorToFormatInternal):
    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return LongVector.write(self.vec, ctx)
