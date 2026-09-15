from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0070_auto_20260909_1604')]

    initial = False

    operations = [
        ops.DeleteModel(name='UploadingFilePart'),
        ops.DeleteModel(name='UploadingFile'),
    ]
