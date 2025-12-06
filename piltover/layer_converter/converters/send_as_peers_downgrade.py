from piltover.layer_converter.converters.base import AutoDowngrader, BaseDowngrader
from piltover.tl.types.channels import SendAsPeers, SendAsPeers_135


class SendAsPeersDowngradeTo135(BaseDowngrader):
    BASE_TYPE = SendAsPeers
    TARGET_LAYER = 135

    @classmethod
    def downgrade(cls, from_obj: SendAsPeers) -> SendAsPeers_135:
        return SendAsPeers_135(
            peers=[p.peer for p in from_obj.peers],
            users=from_obj.users,
            chats=from_obj.chats,
        )


class SendAsPeersDontDowngrade145(AutoDowngrader):
    BASE_TYPE = SendAsPeers
    TARGET_TYPE = SendAsPeers
    TARGET_LAYER = 145
    REMOVE_FIELDS = set()


class SendAsPeersDontDowngrade(AutoDowngrader):
    BASE_TYPE = SendAsPeers
    TARGET_TYPE = SendAsPeers
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
