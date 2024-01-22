from piltover.tl_new import SendAsPeer
from piltover.tl_new.types.channels import SendAsPeers, SendAsPeers_136
from piltover.tl_new.converter import ConverterBase


class SendAsPeersConverter(ConverterBase):
    base = SendAsPeers
    old = [SendAsPeers_136]
    layers = [136]

    @staticmethod
    def from_136(obj: SendAsPeers_136) -> SendAsPeers:
        data = obj.to_dict()
        data["peers"] = [SendAsPeer(peer=peer) for peer in data["peers"]]
        return SendAsPeers(**data)

    @staticmethod
    def to_136(obj: SendAsPeers) -> SendAsPeers_136:
        data = obj.to_dict()
        data["peers"] = [peer.peer for peer in data["peers"]]
        return SendAsPeers_136(**data)

