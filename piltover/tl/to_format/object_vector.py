from piltover.tl import types, TLObjectVector
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class ObjectVectorToFormat(types.internal.ObjectVectorToFormatInternal):
    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return TLObjectVector.write(self.vec, ctx)
