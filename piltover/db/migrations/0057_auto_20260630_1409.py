from typing import TYPE_CHECKING

from loguru import logger
from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps

if TYPE_CHECKING:
    from piltover.db.models import ReadState as ReadStateT, Peer as PeerT


BATCH_SIZE = 1000


async def migrate_out_max_read_id_from_read_state_to_peer(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    ReadState: type[ReadStateT] = apps.get_model("models", "ReadState")
    Peer: type[PeerT] = apps.get_model("models", "Peer")

    base_query = ReadState.all().order_by("id").select_related("peer")
    total_count = await base_query.count()
    processed_count = 0

    offset_id = 0
    while read_states := await base_query.filter(id__gt=offset_id).limit(BATCH_SIZE):
        offset_id = read_states[-1].id
        to_update = []
        for read_state in read_states:
            read_state.peer.out_max_read_id = max(read_state.peer.out_max_read_id, read_state.out_max_read_id)
            to_update.append(read_state.peer)

        if read_states:
            await Peer.bulk_update(to_update, ["out_max_read_id"])

        processed_count += len(read_states)
        logger.info(
            f"Processed {processed_count}/{total_count} "
            f"({processed_count / total_count * 100:.2f}%) read states"
        )


class Migration(migrations.Migration):
    dependencies = [('models', '0056_auto_20260617_1910')]

    initial = False

    operations = [
        ops.AddField(
            model_name='Peer',
            name='out_max_read_id',
            field=fields.BigIntField(default=0),
        ),
        ops.RunPython(
            code=migrate_out_max_read_id_from_read_state_to_peer,
        ),
        ops.RemoveField(model_name='ReadState', name='out_max_read_id'),

    ]
