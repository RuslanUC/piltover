from piltover.tl_new import InputPeerEmpty
from piltover.tl_new.functions.stories import TogglePinned, TogglePinned_160
from piltover.tl_new.converter import ConverterBase


class TogglePinnedConverter(ConverterBase):
    base = TogglePinned
    old = [TogglePinned_160]
    layers = [160]

    @staticmethod
    def from_160(obj: TogglePinned_160) -> TogglePinned:
        data = obj.to_dict()
        data["peer"] = InputPeerEmpty()
        return TogglePinned(**data)

    @staticmethod
    def to_160(obj: TogglePinned) -> TogglePinned_160:
        data = obj.to_dict()
        del data["peer"]
        return TogglePinned_160(**data)

