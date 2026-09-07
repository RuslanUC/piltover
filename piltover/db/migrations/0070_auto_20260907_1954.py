from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0069_auto_20260906_1520')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Channel',
            name='message_seq',
            field=fields.BigIntField(default=0),
        ),
        ops.AddField(
            model_name='MessageDraft',
            name='reply_to_local_id',
            field=fields.BigIntField(null=True),
        ),
        ops.AddField(
            model_name='MessageRef',
            name='local_id',
            field=fields.BigIntField(),
        ),
        ops.AddField(
            model_name='MessageRef',
            name='reply_to_local_id',
            field=fields.BigIntField(null=True),
        ),
        ops.AddField(
            model_name='MessageRef',
            name='top_message_local_id',
            field=fields.BigIntField(null=True),
        ),
        ops.AlterField(
            model_name='Peer',
            name='last_message_id',
            field=fields.BigIntField(null=True),
        ),
        ops.AddField(
            model_name='Peer',
            name='last_message_local_id',
            field=fields.BigIntField(null=True, db_index=True),
        ),
        ops.AddField(
            model_name='User',
            name='message_seq',
            field=fields.BigIntField(default=0),
        ),
    ]
