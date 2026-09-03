from tortoise import fields
from tortoise import migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [('models', '0065_auto_20260902_1633')]

    initial = False

    operations = [
        ops.AddField(
            model_name='MessageRef',
            name='author_id_for_unread_reactions',
            field=fields.BigIntField(default=0),
        ),
        ops.AddField(
            model_name='MessageRef',
            name='reactions_unread_author_id',
            field=fields.BigIntField(null=True),
        ),
        ops.RunSQL(
            """
            UPDATE messageref mref SET author_id_for_unread_reactions = (
                SELECT mc.author_id FROM messagecontent mc WHERE mc.id = mref.content_id
            );
            """
        ),
        ops.RunSQL(
            """
            UPDATE messageref mref SET reactions_unread_author_id = (
                SELECT mc.author_id FROM messagecontent mc WHERE mc.id = mref.content_id AND mc.author_reactions_unread = 1
            );
            """
        ),
        ops.AddIndex(
            model_name='MessageRef',
            index=Index(fields=['reactions_unread_author_id', 'peer_id', 'id']),
        ),
        ops.RemoveField(model_name='MessageContent', name='author_reactions_unread'),
    ]
