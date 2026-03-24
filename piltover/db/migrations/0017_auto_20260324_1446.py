from tortoise import migrations
from tortoise.migrations import operations as ops

class Migration(migrations.Migration):
    dependencies = [('models', '0016_auto_20260324_1431')]

    initial = False

    operations = [
        ops.RemoveField(model_name='AdminLogEntry', name='new_stickerset'),
        ops.RemoveField(model_name='AdminLogEntry', name='old_stickerset'),
    ]
