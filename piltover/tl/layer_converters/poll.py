from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_question_for_133(obj: tl.types.Poll, _: SerializationContext) -> str:
    return obj.question.text
