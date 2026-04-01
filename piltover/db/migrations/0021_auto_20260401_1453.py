from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0020_auto_20260401_1304')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='ChannelUpdate',
            name='pts',
            field=fields.BigIntField(db_index=True),
        ),
        ops.AlterField(
            model_name='Update',
            name='pts',
            field=fields.BigIntField(db_index=True),
        ),
    ]
