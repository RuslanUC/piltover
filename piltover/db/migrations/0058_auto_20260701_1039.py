from tortoise import fields
from tortoise import migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0057_auto_20260630_1409')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageMention',
            name='unread_target_id',
            field=fields.BigIntField(null=True),
        ),
        ops.RemoveField(model_name='MessageMention', name='read'),
        ops.AddIndex(
            model_name='MessageMention',
            index=Index(fields=['user_id', 'unread_target_id']),
        ),
    ]
