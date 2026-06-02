from piltover.layer_converter.converters.base import AutoDowngrader, BaseDowngrader
from piltover.tl import PollAnswer, PollAnswer_133


class PollAnswerDowngradeTo133(BaseDowngrader):
    BASE_TYPE = PollAnswer
    TARGET_LAYER = 133

    @classmethod
    def downgrade(cls, from_obj: PollAnswer) -> PollAnswer_133:
        return PollAnswer_133(
            text=from_obj.text.text,
            option=from_obj.option,
        )


class PollAnswerDontDowngrade(AutoDowngrader):
    BASE_TYPE = PollAnswer
    TARGET_TYPE = PollAnswer
    TARGET_LAYER = TARGET_TYPE.tllayer()
    REMOVE_FIELDS = set()
