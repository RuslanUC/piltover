from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0029_auto_20260421_1718')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageFwdHeader',
            name='internal_random_id',
            field=fields.UUIDField(null=True, unique=True),
        ),
    ]
