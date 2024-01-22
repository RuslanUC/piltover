from piltover.tl_new.types.account import Password, Password_136
from piltover.tl_new.converter import ConverterBase


class PasswordConverter(ConverterBase):
    base = Password
    old = [Password_136]
    layers = [136]

    @staticmethod
    def from_136(obj: Password_136) -> Password:
        data = obj.to_dict()
        return Password(**data)

    @staticmethod
    def to_136(obj: Password) -> Password_136:
        data = obj.to_dict()
        del data["login_email_pattern"]
        return Password_136(**data)

