from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def get_phonecalls_enabled_fallback_for_133(_: tl.types._root._ConfigDowngradable) -> bool:
    return True


def get_ignore_phone_entities_fallback_for_133(_: tl.types._root._ConfigDowngradable) -> bool:
    return False


def get_pfs_enabled_fallback_for_133(_: tl.types._root._ConfigDowngradable) -> bool:
    return True


def get_saved_gifs_limit_fallback_for_133(_: tl.types._root._ConfigDowngradable) -> int:
    return 15


def get_stickers_faved_limit_fallback_for_133(_: tl.types._root._ConfigDowngradable) -> int:
    return 15


def get_pinned_dialogs_count_max_fallback_for_133(_: tl.types._root._ConfigDowngradable) -> int:
    return 5


def get_pinned_infolder_count_max_fallback_for_133(_: tl.types._root._ConfigDowngradable) -> int:
    return 5
