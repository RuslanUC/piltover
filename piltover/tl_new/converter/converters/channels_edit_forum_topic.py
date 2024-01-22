from piltover.tl_new.functions.channels import EditForumTopic, EditForumTopic_148
from piltover.tl_new.converter import ConverterBase


class EditForumTopicConverter(ConverterBase):
    base = EditForumTopic
    old = [EditForumTopic_148]
    layers = [148]

    @staticmethod
    def from_148(obj: EditForumTopic_148) -> EditForumTopic:
        data = obj.to_dict()
        return EditForumTopic(**data)

    @staticmethod
    def to_148(obj: EditForumTopic) -> EditForumTopic_148:
        data = obj.to_dict()
        del data["hidden"]
        return EditForumTopic_148(**data)

