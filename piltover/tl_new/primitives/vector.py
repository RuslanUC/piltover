from __future__ import annotations


class Vector(list):
    value_type: type

    def __init__(self, *args, value_type: type, **kwargs):
        super().__init__(*args, **kwargs)
        self.value_type = value_type
