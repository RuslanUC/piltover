from __future__ import annotations

import piltover.tl_new as tl_new
from piltover.tl_new.utils import classinstancemethod


class Vector(list):
    value_type: type

    def __init__(self, *args, value_type: type, **kwargs):
        super().__init__(*args, **kwargs)
        self.value_type = value_type
