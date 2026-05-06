from tortoise import migrations
from tortoise.migrations import operations as ops

class Migration(migrations.Migration):
    dependencies = [('models', '0034_auto_20260504_1933')]

    initial = False

    operations = [
        ops.RemoveField(model_name='Stickerset', name='access_hash'),
    ]
