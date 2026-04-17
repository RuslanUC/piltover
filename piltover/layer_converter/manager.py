from __future__ import annotations

import copy
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
    def _try_downgrade_list(cls, vec: list[TAny], to_layer: int) -> tuple[list[TAny], bool]:
        if not vec:
            return vec, False

        vec_cls = vec.__class__
        if isinstance(vec[0], list):
            downgraded = False
            result = vec_cls()
            for item in vec:
                new_item, item_downgraded = cls._try_downgrade_list(item, to_layer)
                result.append(new_item)
                downgraded = downgraded or item_downgraded
            return result, downgraded
        if isinstance(vec[0], TLObject):
            downgraded = False
            result = vec_cls()
            for item in vec:
                new_item, item_downgraded = cls._downgrade(item, to_layer)
                result.append(new_item)
                downgraded = downgraded or item_downgraded
            return result, downgraded

        return vec, False

    @classmethod
    def _downgrade(cls, obj: TLObject, to_layer: int) -> tuple[TLObject, bool]:
        downgraded = False
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
            downgraded = True

        if isinstance(obj, list):
            obj, list_downgraded = cls._try_downgrade_list(obj, to_layer)
            return cast(TLObject, obj), list_downgraded or downgraded
        if not isinstance(obj, TLObject):
            assert isinstance(obj, (bool, int, float, str, bytes))
            return cast(TLObject, obj), downgraded

        copied = False

        for obj_cls in obj.__class__.mro():
            slots = getattr(obj_cls, "__slots__", ())
            for slot in slots:
                attr = getattr(obj, slot)
                if isinstance(attr, TLObject):
                    new_attr, attr_downgraded = cls._downgrade(attr, to_layer)
                elif isinstance(attr, list):
                    new_attr, attr_downgraded = cls._try_downgrade_list(attr, to_layer)
                else:
                    continue

                if not attr_downgraded:
                    continue

                downgraded = True
                if not copied:
                    obj = copy.copy(obj)
                    copied = True

                setattr(obj, slot, new_attr)

        return obj, downgraded

    @classmethod
    def downgrade(cls, obj: TLObject, to_layer: int) -> TLObject:
        return cls._downgrade(obj, to_layer)[0]


import piltover.layer_converter.converters as conv
