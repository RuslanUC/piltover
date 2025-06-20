from piltover.layer_converter.converters.base import AutoDowngrader, BaseDowngrader
from piltover.tl import PollAnswer, PollAnswer_136


class PollAnswerDowngradeTo136(BaseDowngrader):
    BASE_TYPE = PollAnswer
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: PollAnswer) -> PollAnswer_136:
        return PollAnswer_136(
            text=from_obj.text.text,
            option=from_obj.option,
        )


class PollAnswerDontDowngrade(AutoDowngrader):
    BASE_TYPE = PollAnswer
    TARGET_LAYER = 201
    TARGET_TYPE = PollAnswer
    REMOVE_FIELDS = set()
