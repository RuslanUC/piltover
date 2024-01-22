from piltover.tl_new.types.stats import BroadcastStats, BroadcastStats_136
from piltover.tl_new.converter import ConverterBase


class BroadcastStatsConverter(ConverterBase):
    base = BroadcastStats
    old = [BroadcastStats_136]
    layers = [136]

    @staticmethod
    def from_136(obj: BroadcastStats_136) -> BroadcastStats:
        data = obj.to_dict()
        assert False, "required field 'story_interactions_graph' added in base tl object"  # TODO: add field
        assert False, "required field 'reactions_per_post' added in base tl object"  # TODO: add field
        assert False, "required field 'views_per_story' added in base tl object"  # TODO: add field
        assert False, "required field 'story_reactions_by_emotion_graph' added in base tl object"  # TODO: add field
        assert False, "required field 'reactions_per_story' added in base tl object"  # TODO: add field
        assert False, "required field 'recent_posts_interactions' added in base tl object"  # TODO: add field
        assert False, "required field 'reactions_by_emotion_graph' added in base tl object"  # TODO: add field
        assert False, "required field 'shares_per_story' added in base tl object"  # TODO: add field
        del data["recent_message_interactions"]
        return BroadcastStats(**data)

    @staticmethod
    def to_136(obj: BroadcastStats) -> BroadcastStats_136:
        data = obj.to_dict()
        del data["story_interactions_graph"]
        del data["reactions_per_post"]
        del data["views_per_story"]
        del data["story_reactions_by_emotion_graph"]
        del data["reactions_per_story"]
        del data["recent_posts_interactions"]
        del data["reactions_by_emotion_graph"]
        del data["shares_per_story"]
        assert False, "required field 'recent_message_interactions' deleted in base tl object"  # TODO: delete field
        return BroadcastStats_136(**data)

