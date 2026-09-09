from tortoise import migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0069_auto_20260906_1520')]

    initial = False

    operations = [
        ops.RemoveIndex(
            model_name='Dialog',
            name=None,
            fields=['owner_id', 'folder_id', 'pinned_index', 'visible'],
        ),
        ops.AddIndex(
            model_name='Dialog',
            index=Index(fields=['owner_id', 'visible', 'folder_id', 'pinned_index']),
        ),
    ]
