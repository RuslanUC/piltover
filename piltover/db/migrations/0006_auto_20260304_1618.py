from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0005_auto_20260303_2001')]

    initial = False

    operations = [
        ops.AddField(
            model_name='ChannelPostInfo',
            name='bulk_id',
            field=fields.BigIntField(null=True, db_index=True),
        ),
    ]
