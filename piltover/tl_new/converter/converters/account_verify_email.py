from piltover.tl_new import EmailVerifyPurposeLoginSetup, EmailVerificationCode
from piltover.tl_new.functions.account import VerifyEmail, VerifyEmail_136
from piltover.tl_new.converter import ConverterBase


class VerifyEmailConverter(ConverterBase):
    base = VerifyEmail
    old = [VerifyEmail_136]
    layers = [136]

    @staticmethod
    def from_136(obj: VerifyEmail_136) -> VerifyEmail:
        data = obj.to_dict()
        data["purpose"] = EmailVerifyPurposeLoginSetup(phone_number="", phone_code_hash="")
        data["verification"] = EmailVerificationCode(obj.code)
        del data["code"]
        del data["email"]
        return VerifyEmail(**data)

    @staticmethod
    def to_136(obj: VerifyEmail) -> VerifyEmail_136:
        data = obj.to_dict()
        data["code"] = obj.verification.code
        data["email"] = ""
        del data["purpose"]
        del data["verification"]
        return VerifyEmail_136(**data)

