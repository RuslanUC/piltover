from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types.auth import Authorization, Authorization_136


class AuthorizationConverter(ConverterBase):
    base = Authorization
    old = [Authorization_136]
    layers = [136]

    @staticmethod
    def from_136(obj: Authorization_136) -> Authorization:
        data = obj.to_dict()
        return Authorization(**data)

    @staticmethod
    def to_136(obj: Authorization) -> Authorization_136:
        data = obj.to_dict()
        del data["future_auth_token"]
        return Authorization_136(**data)
