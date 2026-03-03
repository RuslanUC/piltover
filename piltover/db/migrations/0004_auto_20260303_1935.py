from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0003_auto_20260303_1744')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='send_as_channel',
            field=fields.ForeignKeyField('models.Channel', source_field='send_as_channel_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
