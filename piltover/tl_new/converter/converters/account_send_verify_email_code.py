from piltover.tl_new import EmailVerifyPurposeLoginSetup
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.account import SendVerifyEmailCode, SendVerifyEmailCode_136


class SendVerifyEmailCodeConverter(ConverterBase):
    base = SendVerifyEmailCode
    old = [SendVerifyEmailCode_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendVerifyEmailCode_136) -> SendVerifyEmailCode:
        data = obj.to_dict()
        data["purpose"] = EmailVerifyPurposeLoginSetup(phone_number="", phone_code_hash="")
        return SendVerifyEmailCode(**data)

    @staticmethod
    def to_136(obj: SendVerifyEmailCode) -> SendVerifyEmailCode_136:
        data = obj.to_dict()
        del data["purpose"]
        return SendVerifyEmailCode_136(**data)
