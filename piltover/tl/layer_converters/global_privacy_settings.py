from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_archive_and_mute_new_noncontact_peers_for_133(obj: tl.types.GlobalPrivacySettings, _: SerializationContext) -> bool:
    return obj.archive_and_mute_new_noncontact_peers
