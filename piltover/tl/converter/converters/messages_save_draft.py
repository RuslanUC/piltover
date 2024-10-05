from piltover.tl.converter import ConverterBase
from piltover.tl.functions.messages import SaveDraft, SaveDraft_136, SaveDraft_148


class SaveDraftConverter(ConverterBase):
    base = SaveDraft
    old = [SaveDraft_136, SaveDraft_148]
    layers = [136, 148]

    @staticmethod
    def from_136(obj: SaveDraft_136) -> SaveDraft:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        return SaveDraft(**data)

    @staticmethod
    def to_136(obj: SaveDraft) -> SaveDraft_136:
        data = obj.to_dict()
        del data["invert_media"]
        del data["reply_to"]
        del data["media"]
        return SaveDraft_136(**data)

    @staticmethod
    def from_148(obj: SaveDraft_148) -> SaveDraft:
        data = obj.to_dict()
        del data["reply_to_msg_id"]
        del data["top_msg_id"]
        return SaveDraft(**data)

    @staticmethod
    def to_148(obj: SaveDraft) -> SaveDraft_148:
        data = obj.to_dict()
        del data["invert_media"]
        del data["reply_to"]
        del data["media"]
        return SaveDraft_148(**data)
