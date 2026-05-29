from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0052_auto_20260529_1445')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='Update',
            name='pts',
            field=fields.BigIntField(),
        ),
        ops.AlterField(
            model_name='Update',
            name='related_id',
            field=fields.BigIntField(null=True),
        ),
    ]
