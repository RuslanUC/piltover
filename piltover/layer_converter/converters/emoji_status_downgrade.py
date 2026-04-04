from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import EmojiStatus, EmojiStatus_145, EmojiStatusUntil_145


class EmojiStatusDowngradeTo145(AutoDowngrader):
    BASE_TYPE = EmojiStatus
    TARGET_LAYER = 133

    @classmethod
    def downgrade(cls, from_obj: EmojiStatus) -> EmojiStatus_145 | EmojiStatusUntil_145:
        if from_obj.until is None:
            return EmojiStatus_145(document_id=from_obj.document_id)
        return EmojiStatusUntil_145(document_id=from_obj.document_id, until=from_obj.until)


class EmojiStatusDontDowngrade198(AutoDowngrader):
    BASE_TYPE = EmojiStatus
    TARGET_LAYER = 198
    TARGET_TYPE = EmojiStatus
    REMOVE_FIELDS = set()


class EmojiStatusDontDowngrade(AutoDowngrader):
    BASE_TYPE = EmojiStatus
    TARGET_LAYER = 201
    TARGET_TYPE = EmojiStatus
    REMOVE_FIELDS = set()
