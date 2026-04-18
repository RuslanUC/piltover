from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0027_auto_20260418_1432')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='MessageRef',
            name='random_id',
            field=fields.BigIntField(null=True, db_index=True),
        ),
    ]
