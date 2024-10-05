from piltover.tl.converter import ConverterBase
from piltover.tl.functions.account import RegisterDevice, RegisterDevice_70


class RegisterDeviceConverter(ConverterBase):
    base = RegisterDevice
    old = [RegisterDevice_70]
    layers = [70]

    @staticmethod
    def from_70(obj: RegisterDevice_70) -> RegisterDevice:
        data = obj.to_dict()
        data["app_sandbox"] = False
        data["other_uids"] = []
        data["secret"] = b""
        return RegisterDevice(**data)

    @staticmethod
    def to_70(obj: RegisterDevice) -> RegisterDevice_70:
        data = obj.to_dict()
        del data["no_muted"]
        del data["app_sandbox"]
        del data["flags"]
        del data["other_uids"]
        del data["secret"]
        return RegisterDevice_70(**data)
