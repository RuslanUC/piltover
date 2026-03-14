from __future__ import annotations

from tortoise import fields

from piltover.db.enums import StickersBotState
from piltover.db.models.bot_state_base import BotUserStateBase


class StickersBotUserState(BotUserStateBase):
    state: StickersBotState = fields.IntEnumField(StickersBotState, description="")
