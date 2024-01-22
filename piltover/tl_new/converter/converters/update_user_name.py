from piltover.tl_new.types import UpdateUserName, UpdateUserName_136
from piltover.tl_new.converter import ConverterBase


class UpdateUserNameConverter(ConverterBase):
    base = UpdateUserName
    old = [UpdateUserName_136]
    layers = [136]

    @staticmethod
    def from_136(obj: UpdateUserName_136) -> UpdateUserName:
        data = obj.to_dict()
        assert False, "required field 'usernames' added in base tl object"  # TODO: add field
        del data["username"]
        return UpdateUserName(**data)

    @staticmethod
    def to_136(obj: UpdateUserName) -> UpdateUserName_136:
        data = obj.to_dict()
        del data["usernames"]
        assert False, "required field 'username' deleted in base tl object"  # TODO: delete field
        return UpdateUserName_136(**data)

