from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0038_auto_20260515_1625')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Channel',
            name='admins_count',
            field=fields.SmallIntField(default=0),
        ),
        ops.AddField(
            model_name='Channel',
            name='participants_count',
            field=fields.IntField(default=0),
        ),
        ops.AlterField(
            model_name='Chat',
            name='participants_count',
            field=fields.IntField(default=0),
        ),
    ]
