from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0017_auto_20260324_1446')]

    initial = False

    operations = [
        ops.AddField(
            model_name='AdminLogEntry',
            name='searchable',
            field=fields.CharField(null=True, db_index=True, max_length=8192),
        ),
    ]
