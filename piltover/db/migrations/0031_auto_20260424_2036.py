from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0030_auto_20260424_1848')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='internal_random_id',
            field=fields.UUIDField(null=True, unique=True),
        ),
    ]
