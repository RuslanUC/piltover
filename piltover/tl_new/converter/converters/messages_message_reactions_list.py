from piltover.tl_new import MessagePeerReaction
from piltover.tl_new.types.messages import MessageReactionsList, MessageReactionsList_136
from piltover.tl_new.converter import ConverterBase


class MessageReactionsListConverter(ConverterBase):
    base = MessageReactionsList
    old = [MessageReactionsList_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageReactionsList_136) -> MessageReactionsList:
        data = obj.to_dict()
        data["chats"] = []
        assert False, "type of field 'reactions' changed (Vector<MessageUserReaction> -> Vector<MessagePeerReaction>)"  # TODO: type changed
        return MessageReactionsList(**data)

    @staticmethod
    def to_136(obj: MessageReactionsList) -> MessageReactionsList_136:
        data = obj.to_dict()
        del data["chats"]
        assert False, "type of field 'reactions' changed (Vector<MessagePeerReaction> -> Vector<MessageUserReaction>)"  # TODO: type changed
        return MessageReactionsList_136(**data)

