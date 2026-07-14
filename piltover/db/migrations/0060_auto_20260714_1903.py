from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0059_auto_20260703_1326')]

    initial = False

    operations = [
        ops.AddField(
            model_name='UploadingFile',
            name='part_size',
            field=fields.IntField(default=0),
        ),
    ]
