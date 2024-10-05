from piltover.tl import MessagePeerReaction, MessageUserReaction_136, PeerUser
from piltover.tl.converter import ConverterBase
from piltover.tl.types.messages import MessageReactionsList, MessageReactionsList_136


class MessageReactionsListConverter(ConverterBase):
    base = MessageReactionsList
    old = [MessageReactionsList_136]
    layers = [136]

    @staticmethod
    def from_136(obj: MessageReactionsList_136) -> MessageReactionsList:
        data = obj.to_dict()
        data["chats"] = []
        data["reactions"] = [
            MessagePeerReaction(peer_id=PeerUser(user_id=reaction.user_id), date=0, reaction=reaction.reaction)
            for reaction in obj.reactions
        ]
        return MessageReactionsList(**data)

    @staticmethod
    def to_136(obj: MessageReactionsList) -> MessageReactionsList_136:
        data = obj.to_dict()
        del data["chats"]
        data["reactions"] = [
            MessageUserReaction_136(user_id=reaction.peer_id.user_id, date=0, reaction=reaction.reaction)
            for reaction in obj.reactions if isinstance(reaction.peer_id, PeerUser)
        ]
        return MessageReactionsList_136(**data)
