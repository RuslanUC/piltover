from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0046_fill_dialog_users_20260524_1419')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='Dialog',
            name='owner',
            field=fields.ForeignKeyField('models.User', source_field='owner_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AlterField(
            model_name='MessageDraft',
            name='user',
            field=fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AlterField(
            model_name='ReadState',
            name='owner',
            field=fields.ForeignKeyField('models.User', source_field='owner_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AlterField(
            model_name='SavedDialog',
            name='owner',
            field=fields.ForeignKeyField('models.User', source_field='owner_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
