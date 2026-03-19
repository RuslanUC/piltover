from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0011_auto_20260317_1947')]

    initial = False

    operations = [
        ops.AddField(
            model_name='PrivacyRule',
            name='version',
            field=fields.BigIntField(default=0),
        ),
    ]
