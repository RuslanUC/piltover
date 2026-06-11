from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl
    from piltover.tl.serialization_context import SerializationContext


def downgrade_video_size_max_for_133(obj: tl.types.AutoDownloadSettings, _: SerializationContext) -> int:
    return obj.video_size_max


def downgrade_file_size_max_for_133(obj: tl.types.AutoDownloadSettings, _: SerializationContext) -> int:
    return obj.file_size_max
