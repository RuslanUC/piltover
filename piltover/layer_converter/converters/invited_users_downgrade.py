from piltover.layer_converter.converters.base import AutoDowngrader, BaseDowngrader
from piltover.tl import Updates
from piltover.tl.types.messages import InvitedUsers


class InvitedUsersDowngradeTo136(BaseDowngrader):
    BASE_TYPE = InvitedUsers
    TARGET_LAYER = 136

    @classmethod
    def downgrade(cls, from_obj: InvitedUsers) -> Updates:
        return from_obj.updates


class InvitedUsersDontDowngrade(AutoDowngrader):
    BASE_TYPE = InvitedUsers
    TARGET_TYPE = InvitedUsers
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
