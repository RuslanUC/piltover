from piltover.context import NeedContextValuesContext
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class PollResultsToFormat(types.PollResultsToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
        return LayerConverter.downgrade(
            obj=types.PollResults(
                min=ctx.values is None or ctx.user_id not in ctx.values.poll_answers,
                results=self.results,
                total_voters=self.total_voters,
                # TODO: only show solution if incorrect option was selected
                solution=self.solution,
                solution_entities=self.solution_entities,
            ),
            to_layer=ctx.layer,
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.poll_answers.add(self.id)
