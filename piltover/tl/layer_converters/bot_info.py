from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl


def downgrade_user_id_for_133(obj: tl.types._root._BotInfoDowngradable) -> int:
    if obj.user_id is None:
        return 0
    return obj.user_id


def downgrade_description_for_133(obj: tl.types._root._BotInfoDowngradable) -> str:
    if obj.description is None:
        return ""
    return obj.description


def downgrade_commands_for_133(obj: tl.types._root._BotInfoDowngradable) -> list[tl.base.BotCommand]:
    if obj.commands is None:
        return []
    return obj.commands


def downgrade_menu_button_for_140(obj: tl.types._root._BotInfoDowngradable) -> tl.base.BotMenuButton:
    if obj.menu_button is None:
        return tl.types.BotMenuButtonDefault()
    return obj.menu_button
