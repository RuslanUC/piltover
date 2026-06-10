from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class PollAnswerVotersToFormat(types.PollAnswerVotersToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
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
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)
