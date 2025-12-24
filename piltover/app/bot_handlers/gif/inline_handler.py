import asyncio
from datetime import timedelta, datetime, UTC
from io import BytesIO
from uuid import uuid4, UUID

from fastrand import xorshift128plus_bytes
from httpx import AsyncClient
from loguru import logger

from piltover.app_config import AppConfig
from piltover.context import request_ctx
from piltover.db.enums import FileType, InlineQueryResultType
from piltover.db.models import InlineQuery, File, GifBotFile, InlineQueryResult, InlineQueryResultItem
from piltover.storage import BaseStorage
from piltover.storage.base import StorageType
from piltover.tl import Long
from piltover.utils.utils import run_coro_with_additional_return

_TENOR_SEARCH = "https://tenor.googleapis.com/v2/search"
_TENOR_FEATURED = "https://tenor.googleapis.com/v2/featured"


def _empty(inline_query: InlineQuery) -> tuple[InlineQueryResult, list]:
    result = InlineQueryResult(
        query=inline_query,
        next_offset=None,
        cache_time=60 * 60,
        cache_until=datetime.now(UTC) + timedelta(hours=1),
        gallery=True,
        private=False,
    )
    return result, []


async def _get_or_download_gif(
        tenor_id: str, client: AsyncClient, url: str, storage: BaseStorage, width: int, height: int, duration: float,
) -> File:
    gif_file = await GifBotFile.get_or_none(tenor_id=tenor_id).select_related("file")
    if gif_file is not None:
        return gif_file.file

    physical_id = uuid4()
    part_id = 0
    size = 0

    async with client.stream("GET", url) as resp:
        async for chunk in resp.aiter_bytes(1024 * 1024):
            await storage.save_part(physical_id, part_id, chunk, False)
            part_id += 1
            size += len(chunk)

    file = File(
        physical_id=physical_id,
        mime_type="video/mp4",
        size=size,
        type=FileType.DOCUMENT_GIF,
        constant_access_hash=Long.read_bytes(xorshift128plus_bytes(8)),
        constant_file_ref=UUID(bytes=xorshift128plus_bytes(16)),
        filename=url.rpartition("/")[-1],
        width=width,
        height=height,
        duration=duration,
    )

    await storage.finalize_upload_as(physical_id, StorageType.DOCUMENT, part_id)

    from piltover.app.utils.utils import extract_video_metadata

    location = await storage.documents.get_location(physical_id)
    *_, thumb = await extract_video_metadata(location)
    if thumb is not None:
        thumb_file = BytesIO()
        thumb.save(thumb_file, format="JPEG")
        thumb_bytes = thumb_file.getbuffer()
        await file.make_thumbs(storage, thumb_bytes, False)

    await file.save()
    await GifBotFile.create(tenor_id=tenor_id, file=file)

    return file


async def gif_inline_query_handler(
        inline_query: InlineQuery,
) -> tuple[InlineQueryResult, list[InlineQueryResultItem]] | None:
    if AppConfig.TENOR_KEY is None:
        logger.warning("\"TENOR_API_KEY\" environment variable is not set!")
        return _empty(inline_query)

    storage = request_ctx.get().storage

    url = _TENOR_SEARCH if inline_query.query else _TENOR_FEATURED
    params = {
        "key": AppConfig.TENOR_KEY,
        "limit": "32",
        "media_filter": "mp4",
    }
    if inline_query.query:
        params["q"] = inline_query.query
    # TODO: validate/verify offset
    if inline_query.offset:
        params["pos"] = inline_query.offset

    async with AsyncClient() as cl:
        resp = await cl.get(url, params=params)

        if resp.status_code >= 400:
            logger.warning(f"Failed to get gifs, response code is {resp.status_code}!")
            logger.trace(resp.json())
            return _empty(inline_query)

        data = resp.json()

        if not data["results"]:
            return _empty(inline_query)

        next_offset = str(data["next"]) if data["next"] else None
        coros = []

        for gif in data["results"]:
            if "mp4" not in gif["media_formats"]:
                continue

            gif_id = gif["id"]
            media = gif["media_formats"]["mp4"]

            coros.append(run_coro_with_additional_return(
                _get_or_download_gif(
                    tenor_id=gif_id,
                    client=cl,
                    url=media["url"],
                    storage=storage,
                    width=media["dims"][0],
                    height=media["dims"][1],
                    duration=media["duration"],
                ),
                additional_obj=gif_id,
            ))

        files = await asyncio.gather(*coros)

    result = InlineQueryResult(
        next_offset=next_offset,
        cache_time=60 * 60 * 12,
        cache_until=datetime.now(UTC) + timedelta(hours=1),
        gallery=True,
        private=False,
    )
    items = []

    for file, gif_id in files:
        items.append(InlineQueryResultItem(
            item_id=gif_id,
            position=len(items),
            type=InlineQueryResultType.GIF,
            document=file,
            send_message_text="",
        ))

    return result, items
