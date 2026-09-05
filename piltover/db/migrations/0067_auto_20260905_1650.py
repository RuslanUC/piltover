from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0066_auto_20260903_1639')]

    initial = False

    operations = [
        ops.DeleteModel(name='MessageRelated'),
    ]
