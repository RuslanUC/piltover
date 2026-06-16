from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.migrations.constraints import UniqueConstraint

class Migration(migrations.Migration):
    dependencies = [('models', '0054_auto_20260616_1127')]

    initial = False

    operations = [
        ops.AddConstraint(
            model_name='MessageDraft',
            constraint=UniqueConstraint(fields=('user_id', 'peer_id'), name=None),
        ),
    ]
