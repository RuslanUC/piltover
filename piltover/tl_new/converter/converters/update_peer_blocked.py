from piltover.tl_new.types import UpdatePeerBlocked, UpdatePeerBlocked_136
from piltover.tl_new.converter import ConverterBase


class UpdatePeerBlockedConverter(ConverterBase):
    base = UpdatePeerBlocked
    old = [UpdatePeerBlocked_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdatePeerBlocked_136) -> UpdatePeerBlocked:
        data = obj.to_dict()
        assert False, "type of field 'blocked' changed (Bool -> flags.0?true)"  # TODO: type changed
        return UpdatePeerBlocked(**data)

    @staticmethod
    def to_136(obj: UpdatePeerBlocked) -> UpdatePeerBlocked_136:
        data = obj.to_dict()
        del data["blocked_my_stories_from"]
        del data["flags"]
        assert False, "type of field 'blocked' changed (flags.0?true -> Bool)"  # TODO: type changed
        return UpdatePeerBlocked_136(**data)

