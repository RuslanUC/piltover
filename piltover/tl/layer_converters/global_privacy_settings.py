from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_archive_and_mute_new_noncontact_peers_for_133(obj: tl.types._root._GlobalPrivacySettingsDowngradable) -> bool:
    return obj.archive_and_mute_new_noncontact_peers
