from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0073_auto_20261029_1602')]

    initial = False

    operations = [
        ops.AddField(
            model_name='TaskIqScheduledMessage',
            name='no_webpage',
            field=fields.BooleanField(default=True),
        ),
    ]
