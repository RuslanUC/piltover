from piltover.layer_converter.converters.base import AutoDowngrader, BaseDowngrader
from piltover.tl import Poll, Poll_133


class PollDowngradeTo133(BaseDowngrader):
    BASE_TYPE = Poll
    TARGET_LAYER = 133

    @classmethod
    def downgrade(cls, from_obj: Poll) -> Poll_133:
        return Poll_133(
            id=from_obj.id,
            closed=from_obj.closed,
            public_voters=from_obj.public_voters,
            multiple_choice=from_obj.multiple_choice,
            quiz=from_obj.quiz,
            question=from_obj.question.text,
            # NOTE: Ignoring type because LayerConverter will downgrade all downgradable Poll_136 fields
            answers=from_obj.answers,  # type: ignore
            close_period=from_obj.close_period,
            close_date=from_obj.close_date,
        )


class PollDontDowngrade(AutoDowngrader):
    BASE_TYPE = Poll
    TARGET_LAYER = 201
    TARGET_TYPE = Poll
    REMOVE_FIELDS = set()
