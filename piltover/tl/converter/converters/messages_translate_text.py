from piltover.tl import TextWithEntities
from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import TranslateText, TranslateText_137


class TranslateTextConverter(ConverterBase):
    base = TranslateText
    old = [TranslateText_137]
    layers = [137]

    @staticmethod
    def from_137(obj: TranslateText_137) -> TranslateText:
        data = obj.to_dict()
        del data["from_lang"]
        del data["msg_id"]
        if data["text"] is not None:
            data["text"] = [TextWithEntities(text=data["text"], entities=[])]
        return TranslateText(**data)

    @staticmethod
    def to_137(obj: TranslateText) -> TranslateText_137:
        data = obj.to_dict()
        del data["id"]
        if data["text"] is not None and data["text"]:
            data["text"] = obj.text[0].text
        return TranslateText_137(**data)
