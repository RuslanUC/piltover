from piltover.layer_converter.converters.base import AutoDowngrader, BaseDowngrader
from piltover.tl.types.payments import StarsStatus, StarsStatus_181, StarsStatus_186


class StarsStatusDowngradeTo181(BaseDowngrader):
    BASE_TYPE = StarsStatus
    TARGET_LAYER = 181

    @classmethod
    def downgrade(cls, from_obj: StarsStatus) -> StarsStatus_181:
        return StarsStatus_181(
            balance=from_obj.balance.amount,
            history=from_obj.history,
            next_offset=from_obj.next_offset,
            chats=from_obj.chats,
            users=from_obj.users,
        )


class StarsStatusDowngradeTo186(BaseDowngrader):
    BASE_TYPE = StarsStatus
    TARGET_LAYER = 186

    @classmethod
    def downgrade(cls, from_obj: StarsStatus) -> StarsStatus_186:
        return StarsStatus_186(
            balance=from_obj.balance.amount,
            subscriptions=from_obj.subscriptions,
            subscriptions_next_offset=from_obj.subscriptions_next_offset,
            subscriptions_missing_balance=from_obj.subscriptions_missing_balance,
            history=from_obj.history,
            next_offset=from_obj.next_offset,
            chats=from_obj.chats,
            users=from_obj.users,
        )


class StarsStatusDontDowngrade195(AutoDowngrader):
    BASE_TYPE = StarsStatus
    TARGET_TYPE = StarsStatus
    TARGET_LAYER = 195
    REMOVE_FIELDS = set()


class StarsStatusDontDowngrade(AutoDowngrader):
    BASE_TYPE = StarsStatus
    TARGET_TYPE = StarsStatus
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
