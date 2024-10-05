from piltover.tl.converter import ConverterBase
from piltover.tl.types.messages import SponsoredMessages, SponsoredMessages_136


class SponsoredMessagesConverter(ConverterBase):
    base = SponsoredMessages
    old = [SponsoredMessages_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SponsoredMessages_136) -> SponsoredMessages:
        data = obj.to_dict()
        return SponsoredMessages(**data)

    @staticmethod
    def to_136(obj: SponsoredMessages) -> SponsoredMessages_136:
        data = obj.to_dict()
        del data["posts_between"]
        del data["flags"]
        return SponsoredMessages_136(**data)
