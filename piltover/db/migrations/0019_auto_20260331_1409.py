from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0018_auto_20260329_1343')]

    initial = False

    operations = [
        ops.AddField(
            model_name='ChannelUpdate',
            name='message',
            field=fields.ForeignKeyField('models.MessageRef', source_field='message_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.RemoveField(model_name='ChannelUpdate', name='related_id'),
    ]
