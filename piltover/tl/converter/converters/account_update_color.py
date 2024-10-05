from piltover.tl.converter import ConverterBase
from piltover.tl.functions.account import UpdateColor, UpdateColor_166


class UpdateColorConverter(ConverterBase):
    base = UpdateColor
    old = [UpdateColor_166]
    layers = [166]

    @staticmethod
    def from_166(obj: UpdateColor_166) -> UpdateColor:
        data = obj.to_dict()
        return UpdateColor(**data)

    @staticmethod
    def to_166(obj: UpdateColor) -> UpdateColor_166:
        data = obj.to_dict()
        del data["for_profile"]
        if data["color"] is None:
            data["color"] = 0
        return UpdateColor_166(**data)
