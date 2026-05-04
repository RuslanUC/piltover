from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0033_auto_20260501_1543')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Update',
            name='authorization',
            field=fields.ForeignKeyField('models.UserAuthorization', source_field='authorization_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AddField(
            model_name='Update',
            name='stickerset',
            field=fields.ForeignKeyField('models.Stickerset', source_field='stickerset_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
