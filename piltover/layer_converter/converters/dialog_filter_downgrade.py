from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import DialogFilter, DialogFilter_136


class DialogFilterDowngradeTo136(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter_136
    TARGET_LAYER = 136
    REMOVE_FIELDS = {"color"}


class DialogFilterDontDowngrade(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter
    TARGET_LAYER = 177
    REMOVE_FIELDS = set()
