from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor import BaseSchemaEditor
from tortoise.migrations.schema_generator.state_apps import StateApps

if TYPE_CHECKING:
    from piltover.db.models.peer import Peer as PeerT

BATCH_SIZE = 1000


async def forwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    Peer: type[PeerT] = apps.get_model("models", "Peer")

    base_query = Peer.filter(
        owner_id__isnull=True, channel_id__isnull=False
    ).only("id", "channel_id").order_by("id").limit(BATCH_SIZE)
    total_internal_count = await base_query.count()
    processed_count = 0
    user_peers_count = 0

    offset_id = 0
    while internal_channel_peers := await base_query.filter(id__gt=offset_id):
        offset_id = internal_channel_peers[-1].id
        for channel_peer in internal_channel_peers:
            user_peers_count += await Peer.filter(
                owner_id__isnull=False, channel_id=channel_peer.channel_id
            ).update(channel_peer_id=channel_peer.id)

        processed_count += len(internal_channel_peers)
        logger.info(
            f"Processed {processed_count}/{total_internal_count} "
            f"({processed_count / total_internal_count * 100:.2f}%) internal peers. "
            f"Affected {user_peers_count} user peers"
        )


async def backwards(apps: StateApps, schema_editor: BaseSchemaEditor) -> None:
    Peer: type[PeerT] = apps.get_model("models", "Peer")
    await Peer.all().update(channel_peer_id=None)


class Migration(migrations.Migration):
    dependencies = [('models', '0042_auto_20260522_1447')]

    initial = False

    operations = [
        ops.RunPython(
            code=forwards,
            reverse_code=backwards,
        ),
    ]
