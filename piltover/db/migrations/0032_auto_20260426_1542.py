from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0031_auto_20260424_2036')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Chat',
            name='deleted',
            field=fields.BooleanField(default=False),
        ),
    ]
