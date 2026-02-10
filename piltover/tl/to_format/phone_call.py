from piltover.context import serialization_ctx
from piltover.exceptions import Unreachable
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class PhoneCallToFormat(types.PhoneCallToFormatInternal):
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
                call = types.PhoneCallWaiting(
                    **common_kwargs,
                    protocol=self.protocol,
                )
            elif self.g_a is None:
                call = types.PhoneCallAccepted(
                    **common_kwargs,
                    g_b=self.g_b,
                    protocol=self.protocol,
                )
            else:
                call = types.PhoneCall(
                    **common_kwargs,
                    g_a_or_b=self.g_b,
                    key_fingerprint=self.key_fingerprint or 0,
                    protocol=self.protocol,
                    connections=self.connections or [],
                    start_date=self.start_date or 0,
                )
        elif ctx.user_id == self.participant_id:
            if self.participant_sess_id is None:
                call = types.PhoneCallRequested(
                    **common_kwargs,
                    g_a_hash=self.g_a_hash,
                    protocol=self.protocol,
                )
            elif self.participant_sess_id == ctx.auth_id:
                if self.g_a is None:
                    call = types.PhoneCallWaiting(
                        **common_kwargs,
                        protocol=self.protocol,
                    )
                else:
                    call = types.PhoneCall(
                        **common_kwargs,
                        g_a_or_b=self.g_a,
                        key_fingerprint=self.key_fingerprint or 0,
                        protocol=self.protocol,
                        connections=self.connections or [],
                        start_date=self.start_date or 0,
                    )
            else:
                call = types.PhoneCallDiscarded(
                    id=self.id,
                )
        else:
            raise Unreachable

        return LayerConverter.downgrade(
            obj=call,
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()