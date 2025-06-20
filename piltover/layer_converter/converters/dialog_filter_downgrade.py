from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import DialogFilter, DialogFilter_136, DialogFilter_176


class DialogFilterDowngradeTo136(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter_136
    TARGET_LAYER = 136
    REMOVE_FIELDS = {"color", "title_noanimate"}


class DialogFilterDowngradeTo176(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter_176
    TARGET_LAYER = 176
    REMOVE_FIELDS = {"title_noanimate"}


class DialogFilterDontDowngrade(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
