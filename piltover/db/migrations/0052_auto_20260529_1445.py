from tortoise import migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0051_auto_20260528_1531')]

    initial = False

    operations = [
        ops.AddIndex(
            model_name='Update',
            index=Index(fields=['user_id', 'pts']),
        ),
    ]
