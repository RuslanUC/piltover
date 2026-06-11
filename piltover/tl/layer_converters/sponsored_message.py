from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_show_peer_photo_fallback_for_155(obj: tl.types.SponsoredMessage, _: SerializationContext) -> bool:
    return obj.photo is not None


def get_from_id_fallback_for_133(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> tl.base.Peer:
    return tl.types.PeerUser(user_id=0)


def get_from_id_fallback_for_136(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> tl.base.Peer | None:
    return None


def get_chat_invite_fallback_for_136(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> tl.base.ChatInvite | None:
    return None


def get_chat_invite_hash_fallback_for_136(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> str | None:
    return None


def get_channel_post_fallback_for_134(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> int | None:
    return None


def get_start_param_fallback_for_133(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> str | None:
    return None


def get_webpage_fallback_for_160(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> tl.types.SponsoredWebPage_160 | None:
    return None


def get_app_fallback_for_167(_1: tl.types.SponsoredMessage, _2: SerializationContext) -> tl.base.BotApp | None:
    return None


def downgrade_button_text_for_167(obj: tl.types.SponsoredMessage, _2: SerializationContext) -> str | None:
    return obj.button_text
