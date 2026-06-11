from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def get_phonecalls_enabled_fallback_for_133(_1: tl.types.Config, _2: SerializationContext) -> bool:
    return True


def get_ignore_phone_entities_fallback_for_133(_1: tl.types.Config, _2: SerializationContext) -> bool:
    return False


def get_pfs_enabled_fallback_for_133(_1: tl.types.Config, _2: SerializationContext) -> bool:
    return True


def get_saved_gifs_limit_fallback_for_133(_1: tl.types.Config, _2: SerializationContext) -> int:
    return 100


def get_stickers_faved_limit_fallback_for_133(_1: tl.types.Config, _2: SerializationContext) -> int:
    return 15


def get_pinned_dialogs_count_max_fallback_for_133(_1: tl.types.Config, _2: SerializationContext) -> int:
    return 5


def get_pinned_infolder_count_max_fallback_for_133(_1: tl.types.Config, _2: SerializationContext) -> int:
    return 5
