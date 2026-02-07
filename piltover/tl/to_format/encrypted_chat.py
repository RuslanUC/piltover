from piltover.context import serialization_ctx
from piltover.exceptions import Unreachable
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class EncryptedChatToFormat(types.EncryptedChatToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

        common_kwargs = {
            "id": self.id,
            "access_hash": self.access_hash,
            "date": self.date,
            "admin_id": self.admin_id,
            "participant_id": self.participant_id,
        }

        if ctx.user_id == self.admin_id:
            if self.participant_sess_id is None:
                chat = types.EncryptedChatWaiting(**common_kwargs)
            else:
                chat = types.EncryptedChat(
                    **common_kwargs,
                    g_a_or_b=self.g_b or b"",
                    key_fingerprint=self.key_fingerprint or 0,
                )
        elif ctx.user_id == self.participant_id:
            if self.participant_sess_id is None:
                chat = types.EncryptedChatRequested(
                    **common_kwargs,
                    g_a=self.g_a,
                )
            elif self.participant_sess_id == ctx.auth_id:
                chat = types.EncryptedChat(
                    **common_kwargs,
                    g_a_or_b=self.g_a,
                    key_fingerprint=self.key_fingerprint or 0,
                )
            else:
                chat = types.EncryptedChatDiscarded(
                    id=self.id,
                    history_deleted=True,
                )
        else:
            raise Unreachable

        return LayerConverter.downgrade(
            obj=chat,
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()