from tortoise import Model, fields


class ChannelPostInfo(Model):
    id: int = fields.BigIntField(primary_key=True)
    views: int = fields.BigIntField(default=0)
    forwards: int = fields.BigIntField(default=0)
    bulk_id: int | None = fields.BigIntField(null=True, default=None, db_index=True)
