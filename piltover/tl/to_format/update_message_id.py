from piltover.context import serialization_ctx
from piltover.tl import types, UpdateMessageID


class UpdateMessageIDToFormat(types.UpdateMessageIDToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

        return UpdateMessageID(
            id=self.id,
            random_id=self.random_id if self.target_user == ctx.user_id else 0,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()
