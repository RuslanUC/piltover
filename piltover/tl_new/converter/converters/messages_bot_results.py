from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types.messages import BotResults, BotResults_136


class BotResultsConverter(ConverterBase):
    base = BotResults
    old = [BotResults_136]
    layers = [136]

    @staticmethod
    def from_136(obj: BotResults_136) -> BotResults:
        data = obj.to_dict()
        return BotResults(**data)

    @staticmethod
    def to_136(obj: BotResults) -> BotResults_136:
        data = obj.to_dict()
        del data["switch_webview"]
        return BotResults_136(**data)
