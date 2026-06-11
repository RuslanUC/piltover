from __future__ import annotations
from typing import TYPE_CHECKING
from piltover import tl

if TYPE_CHECKING:
    from piltover.tl.serialization_context import SerializationContext


def get_can_reply_fallback_for_176(obj: tl.types.ConnectedBot, _: SerializationContext) -> bool:
    if obj.rights is None:
        return False
    return obj.rights.reply


def downgrade_recipients_for_176(obj: tl.types.ConnectedBot, _: SerializationContext) -> tl.types.BusinessRecipients:
    return tl.types.BusinessRecipients(
        existing_chats=obj.recipients.existing_chats,
        new_chats=obj.recipients.new_chats,
        contacts=obj.recipients.contacts,
        non_contacts=obj.recipients.non_contacts,
        exclude_selected=obj.recipients.exclude_selected,
        users=obj.recipients.users,
    )
