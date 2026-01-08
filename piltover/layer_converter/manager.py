from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from typing import Callable, TypeVar, cast

from loguru import logger

from piltover.tl import TLObject


T = TypeVar("T", bound=TLObject)
TAny = TypeVar("TAny")


class LayerConverter:
    _down: dict[type[T], dict[int, Callable[[T], TLObject]]] = defaultdict(dict)

    @classmethod
    def register_for_downgrade(cls, downgrader: type[conv.BaseDowngrader]) -> None:
        logger.trace(f"Registered downgrader for type {downgrader.BASE_TYPE.tlname()}, layer {downgrader.TARGET_LAYER}")
        cls._down[downgrader.BASE_TYPE][downgrader.TARGET_LAYER] = downgrader.downgrade

    @classmethod
    def _try_downgrade_list(cls, vec: list[TAny], to_layer: int) -> list[TAny]:
        if not vec:
            return vec

        vec_cls = vec.__class__
        if isinstance(vec[0], list):
            return vec_cls(cls._try_downgrade_list(item, to_layer) for item in vec)
        if isinstance(vec[0], TLObject):
            return vec_cls(cls.downgrade(item, to_layer) for item in vec)

        return vec

    @classmethod
    def downgrade(cls, obj: TLObject, to_layer: int) -> TLObject:
        obj_cls = obj.__class__
        if obj_cls in cls._down:
            if to_layer not in cls._down[obj_cls]:
                layers = list(sorted(cls._down[obj_cls].keys()))
                prev_layer_idx = bisect_left(layers, to_layer) - 1
                if prev_layer_idx < 0:
                    raise RuntimeError(
                        f"Client wants layer {to_layer} for object {obj_cls}, but minimum available is {layers[0]}"
                    )

                prev_layer = layers[prev_layer_idx]
                cls._down[obj_cls][to_layer] = cls._down[obj_cls][prev_layer]

            obj = cls._down[obj.__class__][to_layer](obj)

        if isinstance(obj, list):
            return cast(TLObject, cls._try_downgrade_list(obj, to_layer))
        if not isinstance(obj, TLObject):
            assert isinstance(obj, (bool, int, float, str, bytes))
            return cast(TLObject, obj)

        for slot in obj.__slots__:
            attr = getattr(obj, slot)
            if isinstance(attr, TLObject):
                setattr(obj, slot, cls.downgrade(attr, to_layer))
            elif isinstance(attr, list):
                setattr(obj, slot, cls._try_downgrade_list(attr, to_layer))

        return obj


import piltover.layer_converter.converters as conv
