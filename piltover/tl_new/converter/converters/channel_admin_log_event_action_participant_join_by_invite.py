from piltover.tl_new.types import ChannelAdminLogEventActionParticipantJoinByInvite, ChannelAdminLogEventActionParticipantJoinByInvite_136
from piltover.tl_new.converter import ConverterBase


class ChannelAdminLogEventActionParticipantJoinByInviteConverter(ConverterBase):
    base = ChannelAdminLogEventActionParticipantJoinByInvite
    old = [ChannelAdminLogEventActionParticipantJoinByInvite_136]
    layers = [136]

    @staticmethod
    def from_136(obj: ChannelAdminLogEventActionParticipantJoinByInvite_136) -> ChannelAdminLogEventActionParticipantJoinByInvite:
        data = obj.to_dict()
        return ChannelAdminLogEventActionParticipantJoinByInvite(**data)

    @staticmethod
    def to_136(obj: ChannelAdminLogEventActionParticipantJoinByInvite) -> ChannelAdminLogEventActionParticipantJoinByInvite_136:
        data = obj.to_dict()
        del data["via_chatlist"]
        del data["flags"]
        return ChannelAdminLogEventActionParticipantJoinByInvite_136(**data)

