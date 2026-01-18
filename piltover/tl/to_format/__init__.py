from piltover.context import serialization_ctx, need_values_ctx
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types, Int


class WallPaperToFormat(types.WallPaperToFormatInternal):
    __tl_result_id__ = 0xa437c3ed

    def serialize(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().serialize()

        return types.WallPaper(
            id=self.id,
            creator=self.creator_id == ctx.user_id,
            default=False,
            pattern=self.pattern,
            dark=self.dark,
            access_hash=-1,
            slug=self.slug,
            document=self.document,
            settings=self.settings,
        ).serialize()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return Int.write(self.__tl_result_id__, False) + self.serialize()


class MessageServiceToFormat(types.MessageServiceToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()
        return LayerConverter.downgrade(
            obj=types.MessageService(
                id=self.id,
                peer_id=self.peer_id,
                date=self.date,
                action=self.action,
                out=self.author_id == ctx.user_id,
                reply_to=self.reply_to,
                from_id=self.from_id,
                mentioned=False,
                media_unread=False,
                ttl_period=self.ttl_period,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()


class ThemeToFormat(types.ThemeToFormatInternal):
    def _write(self) -> bytes:
        ctx = serialization_ctx.get()
        return LayerConverter.downgrade(
            obj=types.Theme(
                creator=self.creator_id == ctx.user_id,
                for_chat=self.for_chat,
                id=self.id,
                access_hash=-1,
                slug=self.slug,
                title=self.title,
                document=self.document,
                settings=self.settings,
                emoticon=self.emoticon,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()


class ChatToFormat(types.ChatToFormatInternal):
    def _write(self) -> bytes:
        from piltover.db.models import Chat, Channel
        from piltover.db.models.chat import DEFAULT_ADMIN_RIGHTS

        ctx = serialization_ctx.get()

        if ctx.values is None or self.id not in ctx.values.chat_participants:
            return LayerConverter.downgrade(
                obj=types.ChatForbidden(
                    id=Chat.make_id_from(self.id),
                    title=self.title,
                ),
                to_layer=ctx.layer,
            ).write()

        participant = ctx.values.chat_participants[self.id]
        is_admin = participant.is_admin or self.creator_id == ctx.user_id

        migrated_to = None
        if self.migrated_to is not None:
            migrated_to = types.InputChannel(channel_id=Channel.make_id_from(self.migrated_to), access_hash=-1)

        return LayerConverter.downgrade(
            obj=types.Chat(
                creator=self.creator_id == ctx.user_id,
                left=False,  # ???
                deactivated=self.deactivated,
                noforwards=self.noforwards,
                id=Chat.make_id_from(self.id),
                title=self.title,
                photo=self.photo,
                participants_count=self.participants_count,
                date=self.date,
                version=self.version,
                migrated_to=migrated_to,
                admin_rights=DEFAULT_ADMIN_RIGHTS if is_admin else None,
                default_banned_rights=self.default_banned_rights,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            if (val_ctx := need_values_ctx.get()) is not None:
                val_ctx.chat_participants.add(self.id)
            return super().write()
        return self._write()


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
            if (val_ctx := need_values_ctx.get()) is not None:
                val_ctx.channel_participants.add(self.id)
            return super().write()
        return self._write()
