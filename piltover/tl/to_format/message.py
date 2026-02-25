from piltover.context import serialization_ctx
from piltover.exceptions import Unreachable
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class MessageToFormat(types.MessageToFormatInternal):
    @property
    def id(self) -> int:
        return self.ref.id

    @property
    def media_unread(self) -> bool:
        return self.ref.media_unread

    @media_unread.setter
    def media_unread(self, value: bool) -> None:
        self.ref.media_unread = value

    def _write(self) -> bytes:
        ctx = serialization_ctx.get()

        if isinstance(self.content, types.internal.MessageToFormatContent):
            message = types.Message(
                id=self.ref.id,
                message=self.content.message,
                pinned=self.ref.pinned,
                peer_id=self.ref.peer_id,
                date=self.content.date,
                out=self.ref.out,
                media=self.content.media,
                edit_date=self.content.edit_date,
                reply_to=self.ref.reply_to,
                fwd_from=self.content.fwd_from,
                from_id=self.content.from_id,
                entities=self.content.entities,
                grouped_id=self.content.grouped_id,
                post=self.content.post,
                views=self.content.views,
                forwards=self.content.forwards,
                post_author=self.content.post_author,
                reactions=self.reactions,
                mentioned=self.ref.mentioned,
                media_unread=self.ref.media_unread,
                from_scheduled=self.ref.from_scheduled,
                ttl_period=self.content.ttl_period,
                reply_markup=self.content.reply_markup,
                noforwards=self.content.noforwards,
                via_bot_id=self.content.via_bot_id,
                replies=self.content.replies,
                edit_hide=self.content.edit_hide,
                restriction_reason=[],
            )
        elif isinstance(self.content, types.internal.MessageToFormatServiceContent):
            message = types.MessageService(
                id=self.id,
                peer_id=self.ref.peer_id,
                date=self.content.date,
                action=self.content.action,
                out=self.ref.out,
                reply_to=self.ref.reply_to,
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
