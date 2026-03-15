from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0008_auto_20260310_1545')]

    initial = False

    operations = [
        ops.RunSQL("ALTER TABLE messagecontent DROP FOREIGN KEY fk_messagec_messagec_c7d24d7b;"),
        ops.RunSQL("ALTER TABLE messagecontent DROP FOREIGN KEY fk_messagec_messagec_0121eaf2;"),
        ops.RemoveField(model_name='MessageContent', name='comments_info'),
        ops.RemoveField(model_name='MessageContent', name='discussion'),
        ops.RemoveField(model_name='MessageContent', name='is_discussion'),
        ops.AddField(
            model_name='MessageRef',
            name='discussion',
            field=fields.ForeignKeyField('models.MessageRef', source_field='discussion_id', null=True, db_constraint=True, to_field='id', related_name='msg_discussion_message', on_delete=OnDelete.SET_NULL),
        ),
        ops.AddField(
            model_name='MessageRef',
            name='is_discussion',
            field=fields.BooleanField(default=False),
        ),
        ops.AddField(
            model_name='MessageContent',
            name='replies_version',
            field=fields.IntField(default=0),
        ),
        ops.RunSQL("ALTER TABLE messagecomments DROP FOREIGN KEY fk_messagec_channel_93f4c29f;"),
        ops.RemoveField(model_name='MessageComments', name='discussion_channel'),
        ops.DeleteModel(name='MessageComments'),
    ]
