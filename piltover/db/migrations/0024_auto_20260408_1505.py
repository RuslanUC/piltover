from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0023_auto_20260404_1515')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Update',
            name='message',
            field=fields.ForeignKeyField('models.MessageRef', source_field='message_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
    ]
