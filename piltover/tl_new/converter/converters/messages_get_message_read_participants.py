from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.functions.messages import GetMessageReadParticipants, GetMessageReadParticipants_136


class GetMessageReadParticipantsConverter(ConverterBase):
    base = GetMessageReadParticipants
    old = [GetMessageReadParticipants_136]
    layers = [136]

    @staticmethod
    def from_136(obj: GetMessageReadParticipants_136) -> GetMessageReadParticipants:
        data = obj.to_dict()
        return GetMessageReadParticipants(**data)

    @staticmethod
    def to_136(obj: GetMessageReadParticipants) -> GetMessageReadParticipants_136:
        data = obj.to_dict()
        return GetMessageReadParticipants_136(**data)
