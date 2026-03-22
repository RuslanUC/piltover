from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0012_auto_20260319_1529')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Channel',
            name='stickerset',
            field=fields.ForeignKeyField('models.Stickerset', source_field='stickerset_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.SET_NULL),
        ),
    ]
