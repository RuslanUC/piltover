from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_video_size_max_for_133(obj: tl.types._root._AutoDownloadSettingsDowngradable) -> int:
    return obj.video_size_max


def downgrade_file_size_max_for_133(obj: tl.types._root._AutoDownloadSettingsDowngradable) -> int:
    return obj.file_size_max
