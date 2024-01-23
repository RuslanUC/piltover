from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.account import UnregisterDevice, UnregisterDevice_70


class UnregisterDeviceConverter(ConverterBase):
    base = UnregisterDevice
    old = [UnregisterDevice_70]
    layers = [70]

    @staticmethod
    def from_70(obj: UnregisterDevice_70) -> UnregisterDevice:
        data = obj.to_dict()
        data["other_uids"] = []
        return UnregisterDevice(**data)

    @staticmethod
    def to_70(obj: UnregisterDevice) -> UnregisterDevice_70:
        data = obj.to_dict()
        del data["other_uids"]
        return UnregisterDevice_70(**data)
