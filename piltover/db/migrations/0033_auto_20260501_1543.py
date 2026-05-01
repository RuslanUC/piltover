from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0032_auto_20260426_1542')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Peer',
            name='user_has_wallpaper',
            field=fields.BooleanField(default=False),
        ),
    ]
