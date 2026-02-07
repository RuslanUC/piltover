from piltover.context import serialization_ctx, NeedContextValuesContext
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class ChannelToFormat(types.ChannelToFormatInternal):
    def _forbidden(self, access_hash: int = -1) -> types.ChannelForbidden:
        from piltover.db.models import Channel

        return types.ChannelForbidden(
            id=Channel.make_id_from(self.id),
            access_hash=access_hash,
            title=self.title,
        )

    def _write(self) -> bytes:
        from piltover.db.models import Channel
        from piltover.db.models.channel import CREATOR_RIGHTS
        from piltover.db.enums import PeerType, ChatAdminRights, ChatBannedRights

        ctx = serialization_ctx.get()

        if ctx.values is None or (PeerType.CHANNEL, self.id) not in ctx.values.peers:
            return LayerConverter.downgrade(
                obj=self._forbidden(0),
                to_layer=ctx.layer,
            ).write()

        participant = ctx.values.channel_participants.get(self.id) if ctx.values is not None else None

        if participant is not None and participant.banned_rights & ChatBannedRights.VIEW_MESSAGES:
            return LayerConverter.downgrade(
                obj=self._forbidden(-1),
                to_layer=ctx.layer,
            ).write()

        if participant is None and not (self.nojoin_allow_view or self.username is not None):
            return LayerConverter.downgrade(
                obj=self._forbidden(-1),
                to_layer=ctx.layer,
            ).write()

        admin_rights = None
        if self.creator_id == ctx.user_id:
            admin_rights = CREATOR_RIGHTS
            if participant is not None \
                    and participant.admin_rights & ChatAdminRights.ANONYMOUS == ChatAdminRights.ANONYMOUS:
                admin_rights.anonymous = True
        elif participant is not None and participant.is_admin:
            admin_rights = participant.admin_rights.to_tl()

        return LayerConverter.downgrade(
            obj=types.Channel(
                id=Channel.make_id_from(self.id),
                title=self.title,
                photo=self.photo,
                date=int(participant.invited_at.timestamp()) if participant else self.created_at,
                creator=self.creator_id == ctx.user_id,
                left=participant is None,
                broadcast=self.broadcast,
                megagroup=self.megagroup,
                signatures=self.signatures,
                has_link=self.has_link,
                slowmode_enabled=self.slowmode_enabled,
                noforwards=self.noforwards,
                join_to_send=self.join_to_send,
                join_request=self.join_request,
                stories_hidden=False,
                stories_hidden_min=True,
                stories_unavailable=True,
                access_hash=-1,
                restriction_reason=None,
                admin_rights=admin_rights,
                username=self.username,
                usernames=[],
                default_banned_rights=self.default_banned_rights,
                banned_rights=participant.banned_rights.to_tl() if participant is not None else None,
                color=self.color,
                profile_color=self.profile_color,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.channel_participants.add(self.id)
