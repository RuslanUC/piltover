from tortoise import migrations
from tortoise.migrations import operations as ops

class Migration(migrations.Migration):
    dependencies = [('models', '0048_auto_20260524_1940')]

    initial = False

    operations = [
        ops.RemoveConstraint(
            model_name='ReadHistoryChunk',
            name=None,
            fields=['user_id', 'peer_id'],
        ),
    ]
