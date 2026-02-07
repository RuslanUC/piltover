from piltover.context import serialization_ctx, NeedContextValuesContext
from piltover.exceptions import Unreachable
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class DumbChannelMessageToFormat(types.DumbChannelMessageToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

        if ctx.values is None or self.id not in ctx.values.dumb_messages:
            # TODO: return some empty message?
            raise Unreachable

        return LayerConverter.downgrade(
            obj=ctx.values.dumb_messages[self.id],
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.messages.add(self.id)