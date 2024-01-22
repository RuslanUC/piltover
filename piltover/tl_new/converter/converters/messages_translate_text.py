from piltover.tl_new.functions.messages import TranslateText, TranslateText_137
from piltover.tl_new.converter import ConverterBase


class TranslateTextConverter(ConverterBase):
    base = TranslateText
    old = [TranslateText_137]
    layers = [137]

    @staticmethod
    def from_137(obj: TranslateText_137) -> TranslateText:
        data = obj.to_dict()
        del data["from_lang"]
        del data["msg_id"]
        assert False, "type of field 'text' changed (flags.1?string -> flags.1?Vector<TextWithEntities>)"  # TODO: type changed
        return TranslateText(**data)

    @staticmethod
    def to_137(obj: TranslateText) -> TranslateText_137:
        data = obj.to_dict()
        del data["id"]
        assert False, "type of field 'text' changed (flags.1?Vector<TextWithEntities> -> flags.1?string)"  # TODO: type changed
        return TranslateText_137(**data)

