from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.migrations.constraints import UniqueConstraint


class Migration(migrations.Migration):
    dependencies = [('models', '0067_auto_20260905_1650')]

    initial = False

    operations = [
        ops.RunSQL("UPDATE chatparticipant SET chat_channel_id = chat_id * 2 WHERE chat_id IS NOT NULL;"),
        ops.RunSQL("UPDATE chatparticipant SET chat_channel_id = channel_id * 2 + 1 WHERE channel_id IS NOT NULL;"),
        ops.AlterField(
            model_name='ChatParticipant',
            name='chat_channel_id',
            field=fields.BigIntField(),
        ),
        ops.AddConstraint(
            model_name='ChatParticipant',
            constraint=UniqueConstraint(fields=('user_id', 'chat_channel_id'), name=None),
        ),
    ]
