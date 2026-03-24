from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0015_auto_20260323_1602')]

    initial = False

    operations = [
        ops.AddField(
            model_name='AdminLogEntry',
            name='new_stickerset',
            field=fields.ForeignKeyField('models.Stickerset', source_field='new_stickerset_id', null=True, db_constraint=True, to_field='id', related_name='new_stickerset', on_delete=OnDelete.CASCADE),
        ),
        ops.AddField(
            model_name='AdminLogEntry',
            name='old_stickerset',
            field=fields.ForeignKeyField('models.Stickerset', source_field='old_stickerset_id', null=True, db_constraint=True, to_field='id', related_name='old_stickerset', on_delete=OnDelete.CASCADE),
        ),
    ]
