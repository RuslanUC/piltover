from piltover.context import serialization_ctx
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class PollAnswerVotersToFormat(types.PollAnswerVotersToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

        chosen = (
                ctx.values is not None
                and self.poll_id in ctx.values.poll_answers
                and self.id in ctx.values.poll_answers[self.poll_id]
        )

        return LayerConverter.downgrade(
            obj=types.PollAnswerVoters(
                chosen=chosen,
                correct=self.correct and chosen,
                option=self.option,
                voters=self.voters,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()