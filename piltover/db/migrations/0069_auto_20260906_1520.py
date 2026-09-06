from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0068_auto_20260906_1423')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='MessageRef',
            name='random_id',
            field=fields.BigIntField(null=True),
        ),
    ]
