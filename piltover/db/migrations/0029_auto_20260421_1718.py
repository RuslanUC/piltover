from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.indexes import Index

class Migration(migrations.Migration):
    dependencies = [('models', '0028_auto_20260418_1908')]

    initial = False

    operations = [
        ops.AddIndex(
            model_name='MessageRef',
            index=Index(fields=['peer_id', 'pinned']),
        ),
    ]
