from piltover.context import serialization_ctx, NeedContextValuesContext
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class PollResultsToFormat(types.PollResultsToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

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
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.poll_answers.add(self.id)