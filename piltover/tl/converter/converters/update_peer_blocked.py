from piltover.tl.converter import ConverterBase
from piltover.tl.types import UpdatePeerBlocked, UpdatePeerBlocked_136


class UpdatePeerBlockedConverter(ConverterBase):
    base = UpdatePeerBlocked
    old = [UpdatePeerBlocked_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdatePeerBlocked_136) -> UpdatePeerBlocked:
        data = obj.to_dict()
        return UpdatePeerBlocked(**data)

    @staticmethod
    def to_136(obj: UpdatePeerBlocked) -> UpdatePeerBlocked_136:
        data = obj.to_dict()
        del data["blocked_my_stories_from"]
        del data["flags"]
        return UpdatePeerBlocked_136(**data)
