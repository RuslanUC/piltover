from piltover.tl.converter import ConverterBase
from piltover.tl.functions.account import DeleteAccount, DeleteAccount_136


class DeleteAccountConverter(ConverterBase):
    base = DeleteAccount
    old = [DeleteAccount_136]
    layers = [136]

    @staticmethod
    def from_136(obj: DeleteAccount_136) -> DeleteAccount:
        data = obj.to_dict()
        return DeleteAccount(**data)

    @staticmethod
    def to_136(obj: DeleteAccount) -> DeleteAccount_136:
        data = obj.to_dict()
        del data["password"]
        del data["flags"]
        return DeleteAccount_136(**data)
