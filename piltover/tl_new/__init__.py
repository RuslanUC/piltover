from .primitives import *
from .tl_object import *
from .tl_object import _resolve_annotation, CLASSES_TO_PROCESS
from .types import *
from .functions import *
from .all import *
from inspect import get_annotations

for cls in CLASSES_TO_PROCESS:
    cls_annotations = get_annotations(cls, eval_str=True)
    for field in cls.__tl_fields__:
        if not isinstance(field, TLField):
            continue

        field.type = TLType(*_resolve_annotation(cls_annotations[field.name]))

CLASSES_TO_PROCESS.clear()
