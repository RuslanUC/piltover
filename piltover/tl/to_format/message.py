from piltover.context import serialization_ctx
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types, base


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

    @property
    def reactions(self) -> base.MessageReactions | None:
        return self.content.min_reactions if self.ref.reactions is None else self.ref.reactions

    @reactions.setter
    def reactions(self, value: base.MessageReactions | None) -> None:
        if value is None:
            self.ref.reactions = self.content.min_reactions = None
        elif value.min:
            self.ref.reactions = None
            self.content.min_reactions = value
        else:
            self.ref.reactions = value
            self.content.min_reactions = None

    def _write(self) -> bytes:
        ctx = serialization_ctx.get()
        return LayerConverter.downgrade(
            obj=types.Message(
                id=self.ref.id,
                message=self.content.message,
                pinned=self.ref.pinned,
                peer_id=self.ref.peer_id,
                date=self.content.date,
                out=self.ref.out,
                media=self.content.media,
                edit_date=self.content.edit_date,
                reply_to=self.ref.reply_to,
                fwd_from=self.ref.fwd_from,
                from_id=self.content.from_id,
                entities=self.content.entities,
                grouped_id=self.content.grouped_id,
                post=self.content.post,
                views=self.content.views,
                forwards=self.content.forwards,
                post_author=self.content.post_author,
                reactions=self.content.min_reactions if self.ref.reactions is None else self.ref.reactions,
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
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()
