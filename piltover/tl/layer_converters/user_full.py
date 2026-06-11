from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_premium_gifts_fallback_for_144(_1: tl.types.UserFull, _2: SerializationContext) -> list[tl.base.PremiumGiftOption] | None:
    return None


def get_user_fallback_for_133(_: tl.types.UserFull, ctx: SerializationContext) -> tl.base.User:
    if ctx.layer >= 135:
        return None
    # TODO: base UserFull does not have `user` field
    raise NotImplementedError


def downgrade_stories_for_160(_1: tl.types.UserFull, _2: SerializationContext) -> tl.types.UserStories_160 | None:
    return None
