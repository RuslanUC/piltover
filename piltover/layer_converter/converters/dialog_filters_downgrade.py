from piltover.layer_converter.converters.base import AutoDowngrader, BaseDowngrader
from piltover.tl import DialogFilter
from piltover.tl.types.messages import DialogFilters


class DialogFiltersDowngradeTo136(BaseDowngrader):
    BASE_TYPE = DialogFilters
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: DialogFilters) -> list[DialogFilter]:
        return from_obj.filters


class DialogFiltersDontDowngrade(AutoDowngrader):
    BASE_TYPE = DialogFilters
    TARGET_TYPE = DialogFilters
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
