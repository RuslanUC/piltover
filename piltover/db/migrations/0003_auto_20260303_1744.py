from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0002_auto_20260225_1401')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='anonymous',
            field=fields.BooleanField(default=False),
        ),
    ]
