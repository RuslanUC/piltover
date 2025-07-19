from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import DialogFilter, DialogFilter_136, DialogFilter_176


class DialogFilterDowngradeTo136(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter_136
    TARGET_LAYER = 136
    REMOVE_FIELDS = {"color", "title_noanimate"}

    @classmethod
    def downgrade(cls, from_obj: DialogFilter) -> DialogFilter_136:
        target = super().downgrade(from_obj)
        target.title = from_obj.title.text
        return target


class DialogFilterDowngradeTo176(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter_176
    TARGET_LAYER = 176
    REMOVE_FIELDS = {"title_noanimate"}

    @classmethod
    def downgrade(cls, from_obj: DialogFilter) -> DialogFilter_176:
        target = super().downgrade(from_obj)
        target.title = from_obj.title.text
        return target


class DialogFilterDontDowngrade(AutoDowngrader):
    BASE_TYPE = DialogFilter
    TARGET_TYPE = DialogFilter
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
