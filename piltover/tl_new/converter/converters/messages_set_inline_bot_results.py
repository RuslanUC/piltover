from piltover.tl_new.functions.messages import SetInlineBotResults, SetInlineBotResults_136
from piltover.tl_new.converter import ConverterBase


class SetInlineBotResultsConverter(ConverterBase):
    base = SetInlineBotResults
    old = [SetInlineBotResults_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SetInlineBotResults_136) -> SetInlineBotResults:
        data = obj.to_dict()
        return SetInlineBotResults(**data)

    @staticmethod
    def to_136(obj: SetInlineBotResults) -> SetInlineBotResults_136:
        data = obj.to_dict()
        del data["switch_webview"]
        return SetInlineBotResults_136(**data)

