from __future__ import annotations

from tortoise import fields

from piltover.db.enums import BotFatherState
from piltover.db.models.bot_state_base import BotUserStateBase


class BotFatherUserState(BotUserStateBase):
    state: BotFatherState = fields.IntEnumField(BotFatherState, description="")
