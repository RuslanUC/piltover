from tortoise import Model, fields


class ChannelPostInfo(Model):
    id: int = fields.BigIntField(pk=True)
    views: int = fields.BigIntField(default=0)
    forwards: int = fields.BigIntField(default=0)
