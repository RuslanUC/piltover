import asyncio

from loguru import logger
from tortoise import Tortoise
from tortoise.functions import Count

from piltover.config import TORTOISE_ORM
from piltover.db.models import Stickerset, File

CHUNK_SIZE = 1000


async def _fix_counts() -> None:
    offset_id = 0

    while stickersets := await Stickerset.filter(id__gt=offset_id).limit(CHUNK_SIZE).only("id", "stickers_count"):
        logger.debug(f"Got {len(stickersets)} stickersets from id {offset_id}")

        offset_id = stickersets[-1].id
        stickerset_ids = [stickerset.id for stickerset in stickersets]
        stickers_counts = {
            stickerset_id: stickers_count
            for stickerset_id, stickers_count in await File.filter(
                stickerset_id__in=stickerset_ids,
            ).annotate(count=Count("id")).group_by("stickerset_id").values_list("stickerset_id", "count")
        }

        stickersets_to_update = []
        for stickerset in stickersets:
            if stickerset.id not in stickers_counts:
                logger.info(f"Stickerset {stickerset.id} has not stickers?")
            actual_count = stickers_counts[stickerset.id]
            if stickerset.stickers_count != actual_count:
                stickerset.stickers_count = actual_count
                stickersets_to_update.append(stickerset)

        if stickersets_to_update:
            logger.info(f"Updating {len(stickersets_to_update)} stickersets")
            await Stickerset.bulk_update(stickersets_to_update, ["stickers_count"])


async def main() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await _fix_counts()
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.new_event_loop().run_until_complete(main())
