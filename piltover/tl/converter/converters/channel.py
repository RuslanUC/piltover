from piltover.tl import PeerColor
from piltover.tl.converter import ConverterBase
from piltover.tl.types import Channel, Channel_136, Channel_148, Channel_164, Channel_166


class ChannelConverter(ConverterBase):
    base = Channel
    old = [Channel_136, Channel_148, Channel_164, Channel_166]
    layers = [136, 148, 164, 166]

    @staticmethod
    def from_136(obj: Channel_136) -> Channel:
        data = obj.to_dict()
        return Channel(**data)

    @staticmethod
    def to_136(obj: Channel) -> Channel_136:
        data = obj.to_dict()
        del data["forum"]
        del data["stories_unavailable"]
        del data["stories_hidden_min"]
        del data["flags2"]
        del data["stories_max_id"]
        del data["stories_hidden"]
        del data["color"]
        del data["usernames"]
        return Channel_136(**data)

    @staticmethod
    def from_148(obj: Channel_148) -> Channel:
        data = obj.to_dict()
        return Channel(**data)

    @staticmethod
    def to_148(obj: Channel) -> Channel_148:
        data = obj.to_dict()
        del data["stories_unavailable"]
        del data["stories_hidden_min"]
        del data["stories_max_id"]
        del data["stories_hidden"]
        del data["color"]
        return Channel_148(**data)

    @staticmethod
    def from_164(obj: Channel_164) -> Channel:
        data = obj.to_dict()
        return Channel(**data)

    @staticmethod
    def to_164(obj: Channel) -> Channel_164:
        data = obj.to_dict()
        del data["color"]
        return Channel_164(**data)

    @staticmethod
    def from_166(obj: Channel_166) -> Channel:
        data = obj.to_dict()
        del data["background_emoji_id"]
        if data["color"] is not None:
            data["color"] = PeerColor(color=data["color"])
        return Channel(**data)

    @staticmethod
    def to_166(obj: Channel) -> Channel_166:
        data = obj.to_dict()
        if data["color"] is not None:
            data["color"] = obj.color.color
        return Channel_166(**data)
