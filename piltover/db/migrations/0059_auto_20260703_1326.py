from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0058_auto_20260701_1039')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageContent',
            name='can_see_reactions_list',
            field=fields.BooleanField(default=False),
        ),
    ]
