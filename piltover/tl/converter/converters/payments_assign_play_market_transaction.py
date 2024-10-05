from piltover.tl import DataJSON
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.payments import AssignPlayMarketTransaction, AssignPlayMarketTransaction_143


class AssignPlayMarketTransactionConverter(ConverterBase):
    base = AssignPlayMarketTransaction
    old = [AssignPlayMarketTransaction_143]
    layers = [143]

    @staticmethod
    def from_143(obj: AssignPlayMarketTransaction_143) -> AssignPlayMarketTransaction:
        data = obj.to_dict()
        data["receipt"] = DataJSON(data="{}")
        del data["purchase_token"]
        return AssignPlayMarketTransaction(**data)

    @staticmethod
    def to_143(obj: AssignPlayMarketTransaction) -> AssignPlayMarketTransaction_143:
        data = obj.to_dict()
        del data["purpose"]
        del data["receipt"]
        data["purchase_token"] = ""
        return AssignPlayMarketTransaction_143(**data)
