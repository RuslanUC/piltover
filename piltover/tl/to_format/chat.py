from piltover.context import NeedContextValuesContext
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class ChatToFormat(types.ChatToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
        from piltover.db.models import Chat, Channel
        from piltover.db.models.chat import DEFAULT_ADMIN_RIGHTS

        if ctx.values is None or self.id not in ctx.values.chat_participants:
            return LayerConverter.downgrade(
                obj=types.ChatForbidden(
                    id=Chat.make_id_from(self.id),
                    title=self.title,
                ),
                to_layer=ctx.layer,
            ).write(ctx)

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
                photo=self.photo if self.photo else types.ChatPhotoEmpty(),
                participants_count=self.participants_count,
                date=self.date,
                version=self.version,
                migrated_to=migrated_to,
                admin_rights=DEFAULT_ADMIN_RIGHTS if is_admin else None,
                default_banned_rights=self.default_banned_rights,
            ),
            to_layer=ctx.layer,
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.chat_participants.add(self.id)
