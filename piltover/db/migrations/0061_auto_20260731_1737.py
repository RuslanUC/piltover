from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0060_auto_20260628_1800')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='reply_quote_offset',
            field=fields.IntField(null=True),
        ),
        ops.AddField(
            model_name='MessageContent',
            name='reply_quote_text',
            field=fields.TextField(null=True, unique=False),
        ),
    ]
