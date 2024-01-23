from piltover.tl_new import Username
from piltover.tl_new.converter import ConverterBase
from piltover.tl_new.types import UpdateUserName, UpdateUserName_136


class UpdateUserNameConverter(ConverterBase):
    base = UpdateUserName
    old = [UpdateUserName_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateUserName_136) -> UpdateUserName:
        data = obj.to_dict()
        data["usernames"] = [Username(username=obj.username)]
        del data["username"]
        return UpdateUserName(**data)

    @staticmethod
    def to_136(obj: UpdateUserName) -> UpdateUserName_136:
        data = obj.to_dict()
        del data["usernames"]
        data["username"] = obj.usernames[0].username
        return UpdateUserName_136(**data)
