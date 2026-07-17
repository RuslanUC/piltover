from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0060_auto_20260628_1800')]

    initial = False

    operations = [
        ops.DeleteModel(name='MessageRelated'),
    ]
