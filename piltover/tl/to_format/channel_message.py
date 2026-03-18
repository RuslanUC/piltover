from piltover.context import serialization_ctx, NeedContextValuesContext
from piltover.exceptions import Unreachable
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class ChannelMessageToFormat(types.ChannelMessageToFormatInternal):
    def _write(self) -> bytes:
        from piltover.db import models

        ctx = serialization_ctx.get()

        peer = types.PeerChannel(channel_id=models.Channel.make_id_from(self.common.channel_id))

        if ctx.values is None or self.common.id not in ctx.values.channel_messages:
            reactions = None
            mentioned = False
            media_unread = False
        else:
            reactions, mentioned, media_unread = ctx.values.channel_messages[self.common.id]

        if isinstance(self.content, types.internal.MessageToFormatContent):
            message = types.Message(
                id=self.common.id,
                message=self.content.message,
                pinned=self.common.pinned,
                peer_id=peer,
                date=self.content.date,
                out=self.common.author_id == ctx.user_id,
                media=self.content.media,
                edit_date=self.content.edit_date,
                reply_to=self.common.reply_to,
                fwd_from=self.content.fwd_from,
                from_id=self.content.from_id,
                entities=self.content.entities,
                grouped_id=self.content.grouped_id,
                post=self.content.post,
                views=self.content.views,
                forwards=self.content.forwards,
                post_author=self.content.post_author,
                reactions=reactions,
                mentioned=mentioned,
                media_unread=media_unread,
                from_scheduled=self.common.from_scheduled if self.common.author_id == ctx.user_id else False,
                ttl_period=self.content.ttl_period,
                reply_markup=self.content.reply_markup,
                noforwards=self.content.noforwards,
                via_bot_id=self.content.via_bot_id,
                replies=self.replies,
                edit_hide=self.content.edit_hide,
                restriction_reason=[],
            )
        elif isinstance(self.content, types.internal.MessageToFormatServiceContent):
            message = types.MessageService(
                id=self.common.id,
                peer_id=peer,
                date=self.content.date,
                action=self.content.action,
                out=self.common.author_id == ctx.user_id,
                reply_to=self.common.reply_to,
                from_id=self.content.from_id,
                mentioned=False,  # TODO: ?
                media_unread=False,  # TODO: ?
                ttl_period=self.content.ttl_period,
            )
        else:
            raise Unreachable

        return LayerConverter.downgrade(obj=message, to_layer=ctx.layer).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.channel_messages.add(self.common.id)
