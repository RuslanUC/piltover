from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0001_initial')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageReaction',
            name='date',
            field=fields.DatetimeField(auto_now=False, auto_now_add=True),
        ),
    ]
