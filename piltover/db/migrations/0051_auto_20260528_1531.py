from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.indexes import Index

class Migration(migrations.Migration):
    dependencies = [('models', '0050_auto_20260525_1946')]

    initial = False

    operations = [
        ops.AddIndex(
            model_name='Dialog',
            index=Index(fields=['owner_id', 'folder_id', 'pinned_index', 'visible']),
        ),
    ]
