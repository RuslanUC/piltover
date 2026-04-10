from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0025_auto_20260408_1639')]

    initial = False

    operations = [
        ops.AddField(
            model_name='UploadingFile',
            name='state',
            field=fields.BinaryField(null=True),
        ),
        ops.AddField(
            model_name='UploadingFilePart',
            name='state',
            field=fields.BinaryField(null=True),
        ),
    ]
