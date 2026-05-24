from typing import TYPE_CHECKING

from tortoise import fields
from tortoise import migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops
from tortoise.migrations.constraints import UniqueConstraint
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps

if TYPE_CHECKING:
    from piltover.db.models import ReadHistoryChunk as ReadHistoryChunkT, Peer as PeerT


BATCH_SIZE = 1000


async def remove_read_history_chunks(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    ReadHistoryChunk: type[ReadHistoryChunkT] = apps.get_model("models", "ReadHistoryChunk")
    await ReadHistoryChunk.all().delete()


async def remove_user_channel_peers(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    Peer: type[PeerT] = apps.get_model("models", "Peer")
    await Peer.filter(owner_id__isnull=False, channel_id__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [('models', '0047_auto_20260524_1505')]

    initial = False

    operations = [
        ops.RunPython(remove_read_history_chunks),
        ops.RunPython(remove_user_channel_peers),
        ops.RemoveConstraint(
            model_name='Peer',
            name=None,
            fields=['owner', 'channel'],
        ),
        ops.AlterField(
            model_name='Peer',
            name='channel',
            field=fields.OneToOneField('models.Channel', source_field='channel_id', null=True, db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.RemoveField(model_name='Peer', name='channel_peer'),
        ops.AddField(
            model_name='ReadHistoryChunk',
            name='user',
            field=fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', on_delete=OnDelete.CASCADE),
        ),
        ops.AddConstraint(
            model_name='ReadHistoryChunk',
            constraint=UniqueConstraint(fields=('user_id', 'peer_id'), name=None),
        ),
    ]
