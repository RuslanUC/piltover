from piltover.tl.converter import ConverterBase
from piltover.tl.functions.channels import DeleteHistory, DeleteHistory_136


class DeleteHistoryConverter(ConverterBase):
    base = DeleteHistory
    old = [DeleteHistory_136]
    layers = [136]

    @staticmethod
    def from_136(obj: DeleteHistory_136) -> DeleteHistory:
        data = obj.to_dict()
        return DeleteHistory(**data)

    @staticmethod
    def to_136(obj: DeleteHistory) -> DeleteHistory_136:
        data = obj.to_dict()
        del data["for_everyone"]
        del data["flags"]
        return DeleteHistory_136(**data)
