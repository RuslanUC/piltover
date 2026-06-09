from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from piltover import tl


def downgrade_size_for_133(obj: tl.types._root._EncryptedFileDowngradable) -> int:
    return obj.size
