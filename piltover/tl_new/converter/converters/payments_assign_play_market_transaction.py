from piltover.tl_new.functions.payments import AssignPlayMarketTransaction, AssignPlayMarketTransaction_143
from piltover.tl_new.converter import ConverterBase


class AssignPlayMarketTransactionConverter(ConverterBase):
    base = AssignPlayMarketTransaction
    old = [AssignPlayMarketTransaction_143]
    layers = [143]

    @staticmethod
    def from_143(obj: AssignPlayMarketTransaction_143) -> AssignPlayMarketTransaction:
        data = obj.to_dict()
        assert False, "required field 'purpose' added in base tl object"  # TODO: add field
        assert False, "required field 'receipt' added in base tl object"  # TODO: add field
        del data["purchase_token"]
        return AssignPlayMarketTransaction(**data)

    @staticmethod
    def to_143(obj: AssignPlayMarketTransaction) -> AssignPlayMarketTransaction_143:
        data = obj.to_dict()
        del data["purpose"]
        del data["receipt"]
        assert False, "required field 'purchase_token' deleted in base tl object"  # TODO: delete field
        return AssignPlayMarketTransaction_143(**data)

