from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.indexes import Index

class Migration(migrations.Migration):
    dependencies = [('models', '0040_auto_20260522_1243')]

    initial = False

    operations = [
        ops.AddIndex(
            model_name='MessageRef',
            index=Index(fields=['peer_id', 'id']),
        ),
    ]
