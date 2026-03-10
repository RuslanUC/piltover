from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0007_auto_20260307_1814')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='author_reactions_unread',
            field=fields.BooleanField(default=False),
        ),
        ops.RemoveField(model_name='ReadState', name='last_reaction_id'),
    ]
