from __future__ import annotations

from tortoise import fields, Model

from piltover.tl.types.help import PeerColorProfileSet, PeerColorSet, PeerColorOption as TLPeerColorOption


class PeerColorOption(Model):
    id: int = fields.BigIntField(pk=True)
    hidden: bool = fields.BooleanField(default=False)
    is_profile: bool = fields.BooleanField()

    # peerColorOption.colors:
    # peerColorSet.colors[0] or peerColorProfileSet.palette_colors[0]
    color1: int = fields.IntField()
    # peerColorSet.colors[1] or peerColorProfileSet.palette_colors[1]
    color2: int | None = fields.IntField(null=True, default=None)
    # peerColorSet.colors[2] or peerColorProfileSet.bg_colors[0]
    color3: int | None = fields.IntField(null=True, default=None)
    # peerColorProfileSet.bg_colors[1]
    color4: int | None = fields.IntField(null=True, default=None)
    # peerColorProfileSet.story_colors[0]
    color5: int | None = fields.IntField(null=True, default=None)
    # peerColorProfileSet.story_colors[1]
    color6: int | None = fields.IntField(null=True, default=None)

    # peerColorOption.dark_colors:
    # peerColorSet.colors[0] or peerColorProfileSet.palette_colors[0]
    dark_color1: int | None = fields.IntField(null=True, default=None)
    # peerColorSet.colors[1] or peerColorProfileSet.palette_colors[1]
    dark_color2: int | None = fields.IntField(null=True, default=None)
    # peerColorSet.colors[2] or peerColorProfileSet.bg_colors[0]
    dark_color3: int | None = fields.IntField(null=True, default=None)
    # peerColorProfileSet.bg_colors[1]
    dark_color4: int | None = fields.IntField(null=True, default=None)
    # peerColorProfileSet.story_colors[0]
    dark_color5: int | None = fields.IntField(null=True, default=None)
    # peerColorProfileSet.story_colors[1]
    dark_color6: int | None = fields.IntField(null=True, default=None)

    def to_peer_color_set(
            self, c1: int, c2: int | None, c3: int | None, c4: int | None, c5: int | None, c6: int | None,
    ) -> PeerColorSet | PeerColorProfileSet:
        if self.is_profile:
            color_set = PeerColorProfileSet(palette_colors=[c1], bg_colors=[], story_colors=[])
            if c2:
                color_set.palette_colors.append(c2)
            if c3:
                color_set.bg_colors.append(c3)
            if c4:
                color_set.bg_colors.append(c4)
            if c5:
                color_set.story_colors.append(c5)
            if c6:
                color_set.story_colors.append(c6)

            return color_set

        color_set = PeerColorSet(colors=[c1])
        if c2:
            color_set.colors.append(c2)
        if c3:
            color_set.colors.append(c3)

        return color_set

    def to_tl(self) -> TLPeerColorOption:
        return TLPeerColorOption(
            color_id=self.id,
            hidden=self.hidden,
            colors=self.to_peer_color_set(
                self.color1, self.color2, self.color3,
                self.color4, self.color5, self.color6,
            ) if self.id > 6 else None,
            dark_colors=self.to_peer_color_set(
                self.dark_color1, self.dark_color2, self.dark_color3,
                self.dark_color4, self.dark_color5, self.dark_color6,
            ) if self.dark_color1 is not None else None,
        )
