from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0055_auto_20260616_1900')]

    initial = False

    operations = [
        ops.AddField(
            model_name='ReadState',
            name='out_max_read_id',
            field=fields.BigIntField(default=0),
        ),
    ]
