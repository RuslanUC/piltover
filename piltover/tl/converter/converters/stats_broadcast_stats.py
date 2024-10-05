from piltover.tl import StatsGraph, DataJSON, StatsAbsValueAndPrev
from piltover.tl.converter import ConverterBase
from piltover.tl.types.stats import BroadcastStats, BroadcastStats_136


class BroadcastStatsConverter(ConverterBase):
    base = BroadcastStats
    old = [BroadcastStats_136]
    layers = [136]

    @staticmethod
    def from_136(obj: BroadcastStats_136) -> BroadcastStats:
        data = obj.to_dict()
        data["story_interactions_graph"] = StatsGraph(json=DataJSON(data="{}"))
        data["reactions_per_post"] = StatsAbsValueAndPrev(current=0, previous=0)
        data["views_per_story"] = StatsAbsValueAndPrev(current=0, previous=0)
        data["reactions_per_story"] = StatsAbsValueAndPrev(current=0, previous=0)
        data["story_reactions_by_emotion_graph"] = StatsGraph(json=DataJSON(data="{}"))
        data["recent_posts_interactions"] = []
        data["reactions_by_emotion_graph"] = StatsGraph(json=DataJSON(data="{}"))
        data["shares_per_story"] = StatsAbsValueAndPrev(current=0, previous=0)
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
        data["recent_message_interactions"] = []
        return BroadcastStats_136(**data)
