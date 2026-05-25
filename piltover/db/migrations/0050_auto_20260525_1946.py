from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields

_LAST_MESSAGE_SYNC_SQL = """
UPDATE peer
SET
    last_message_id = (
        SELECT m.id
        FROM messageref m
        INNER JOIN messagecontent mc ON m.content_id = mc.id
        WHERE m.peer_id = peer.id
        ORDER BY m.id DESC
        LIMIT 1
    ),
    last_message_date = (
        SELECT mc.date
        FROM messageref m
        INNER JOIN messagecontent mc ON m.content_id = mc.id
        WHERE m.peer_id = peer.id
        ORDER BY m.id DESC
        LIMIT 1
    )
WHERE last_message_id IS NULL OR last_message_date IS NULL;
"""


class Migration(migrations.Migration):
    dependencies = [('models', '0049_auto_20260524_2002')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Peer',
            name='last_message_date',
            field=fields.DatetimeField(null=True, db_index=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name='Peer',
            name='last_message_id',
            field=fields.BigIntField(null=True, db_index=True),
        ),
        ops.RunSQL(_LAST_MESSAGE_SYNC_SQL),
    ]
