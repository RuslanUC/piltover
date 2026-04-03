from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0021_auto_20260401_1453')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Update',
            name='dialog',
            field=fields.ForeignKeyField('models.Dialog', source_field='dialog_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AddField(
            model_name='Update',
            name='update_user',
            field=fields.ForeignKeyField('models.User', source_field='update_user_id', null=True, db_constraint=True, to_field='id', related_name='updated', on_delete=OnDelete.CASCADE),
        ),
    ]
