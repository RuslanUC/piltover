from piltover.tl_new.functions.auth import SignIn, SignIn_136
from piltover.tl_new.converter import ConverterBase


class SignInConverter(ConverterBase):
    base = SignIn
    old = [SignIn_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SignIn_136) -> SignIn:
        data = obj.to_dict()
        return SignIn(**data)

    @staticmethod
    def to_136(obj: SignIn) -> SignIn_136:
        data = obj.to_dict()
        del data["email_verification"]
        del data["flags"]
        if data["phone_code"] is None:
            data["phone_code"] = ""
        return SignIn_136(**data)

