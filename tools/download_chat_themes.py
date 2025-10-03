import argparse
import json
import shutil
from asyncio import get_event_loop
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from loguru import logger
from pyrogram import Client
from pyrogram.file_id import FileId, FileType, ThumbnailSource
from pyrogram.raw.core import TLObject
from pyrogram.raw.functions.account import GetChatThemes
from pyrogram.raw.types import Document, PhotoSize, PhotoPathSize, Theme, ThemeSettings, WallPaper
from pyrogram.raw.types.account import Themes


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    data_dir: Path


def doc_to_fileid(doc: Document, thumb: PhotoSize | None = None) -> FileId:
    return FileId(
        major=FileId.MAJOR,
        minor=FileId.MINOR,
        file_type=FileType.DOCUMENT if thumb is None else FileType.THUMBNAIL,
        dc_id=doc.dc_id,
        file_reference=doc.file_reference,
        media_id=doc.id,
        access_hash=doc.access_hash,

        thumbnail_source=None if thumb is None else ThumbnailSource.THUMBNAIL,
        thumbnail_file_type=None if thumb is None else FileType.STICKER,
        thumbnail_size="" if thumb is None else thumb.type,
    )


async def download_document(client: Client, idx: int, doc: Document, out_dir: Path) -> None:
    await client.handle_download(
        (
            doc_to_fileid(doc),
            str(out_dir / "files"),
            f"{doc.id}-{idx}.{doc.mime_type.split('/')[-1]}",
            False,
            doc.size,
            None,
            (),
        )
    )

    for thumb in doc.thumbs:
        if isinstance(thumb, PhotoPathSize):
            with open(out_dir / f"files/{doc.id}-{idx}-thumb-{thumb.type}.bin", "wb") as f:
                f.write(thumb.bytes)
        elif isinstance(thumb, PhotoSize):
            await client.handle_download(
                (
                    doc_to_fileid(doc, thumb),
                    str(out_dir / "files"),
                    f"{doc.id}-{idx}-thumb-{thumb.type}.{doc.mime_type.split('/')[-1]}",
                    False,
                    doc.size,
                    None,
                    (),
                )
            )
        else:
            print(f"Unknown thumb type: {thumb}")


async def extract_chat_themes(client: Client, out_dir: Path) -> None:
    themes: Themes = await client.invoke(GetChatThemes(hash=0))
    logger.info(f"Got {len(themes.themes)} themes")
    for idx, theme in enumerate(cast(list[Theme], themes.themes)):
        logger.info(f"Downloading theme \"{theme.title}\"")
        for settings in cast(list[ThemeSettings], theme.settings):
            if settings.wallpaper is not None:
                await download_document(client, idx, cast(WallPaper, settings.wallpaper).document, out_dir)

        with open(out_dir / f"{idx}.json", "w") as f:
            json.dump(theme, f, indent=4, default=TLObject.default, ensure_ascii=False)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-id", required=False, type=int, help="Telegram api id")
    parser.add_argument("--api-hash", required=False, type=str, help="Telegram api hash")
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory to where chat themes will be download",
                        default=Path("./data").resolve())
    args = parser.parse_args(namespace=ArgsNamespace())

    out_dir = args.data_dir / "chat_themes"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / ".gitignore", "w") as f:
        f.write("*\n")

    async with Client(
            name="telegram", api_id=args.api_id, api_hash=args.api_hash, workdir=str(args.data_dir / "secrets"),
    ) as client:
        await extract_chat_themes(client, out_dir)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
