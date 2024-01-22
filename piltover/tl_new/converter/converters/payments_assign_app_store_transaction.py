from piltover.tl_new.functions.payments import AssignAppStoreTransaction, AssignAppStoreTransaction_143
from piltover.tl_new.converter import ConverterBase


class AssignAppStoreTransactionConverter(ConverterBase):
    base = AssignAppStoreTransaction
    old = [AssignAppStoreTransaction_143]
    layers = [143]

    @staticmethod
    def from_143(obj: AssignAppStoreTransaction_143) -> AssignAppStoreTransaction:
        data = obj.to_dict()
        assert False, "required field 'purpose' added in base tl object"  # TODO: add field
        del data["restore"]
        del data["flags"]
        return AssignAppStoreTransaction(**data)

    @staticmethod
    def to_143(obj: AssignAppStoreTransaction) -> AssignAppStoreTransaction_143:
        data = obj.to_dict()
        del data["purpose"]
        return AssignAppStoreTransaction_143(**data)

