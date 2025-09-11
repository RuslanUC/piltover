import argparse
import json
import shutil
from asyncio import get_event_loop
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from loguru import logger
from pyrogram import Client
from pyrogram.file_id import FileId, FileType, ThumbnailSource
from pyrogram.raw.core import TLObject
from pyrogram.raw.functions.messages import GetAvailableReactions
from pyrogram.raw.types import AvailableReaction, Document, DocumentAttributeSticker, PhotoSize, PhotoPathSize
from pyrogram.raw.types.messages import AvailableReactions


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    data_dir: Path


def doc_to_fileid(doc: Document, thumb: PhotoSize | None = None) -> FileId:
    return FileId(
        major=FileId.MAJOR,
        minor=FileId.MINOR,
        file_type=FileType.STICKER if thumb is None else FileType.THUMBNAIL,
        dc_id=doc.dc_id,
        file_reference=doc.file_reference,
        media_id=doc.id,
        access_hash=doc.access_hash,

        thumbnail_source=None if thumb is None else ThumbnailSource.THUMBNAIL,
        thumbnail_file_type=None if thumb is None else FileType.STICKER,
        thumbnail_size="" if thumb is None else thumb.type,
    )


async def download_reaction(client: Client, idx: int, doc: Document, out_dir: Path) -> None:
    assert any(filter(lambda attr: isinstance(attr, DocumentAttributeSticker), doc.attributes))

    await client.handle_download(
        (
            doc_to_fileid(doc),
            out_dir / "files",
            f"{doc.id}-{idx}.{doc.mime_type.split('/')[-1]}",
            False,
            doc.size,
            None,
            (),
        )
    )

    for thumb in doc.thumbs:
        if isinstance(thumb, PhotoPathSize):
            with open(out_dir / "files" / f"{doc.id}-{idx}-thumb-{thumb.type}.bin", "wb") as f:
                f.write(thumb.bytes)
        elif isinstance(thumb, PhotoSize):
            await client.handle_download(
                (
                    doc_to_fileid(doc, thumb),
                    out_dir / "files",
                    f"{doc.id}-{idx}-thumb-{thumb.type}.{doc.mime_type.split('/')[-1]}",
                    False,
                    doc.size,
                    None,
                    (),
                )
            )
        else:
            logger.warning(f"Unknown thumb type: {thumb}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-id", required=False, type=int, help="Telegram api id")
    parser.add_argument("--api-hash", required=False, type=str, help="Telegram api hash")
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory to where reactions will be download",
                        default=Path("./data").resolve())
    args = parser.parse_args(namespace=ArgsNamespace())

    reactions_dir = args.data_dir / "reactions"
    if reactions_dir.exists():
        shutil.rmtree(reactions_dir)
    reactions_dir.mkdir(parents=True, exist_ok=True)

    async with Client(
            name="telegram", api_id=args.api_id, api_hash=args.api_hash, workdir=str(args.data_dir / "secrets"),
    ) as client:
        reactions: AvailableReactions = await client.invoke(GetAvailableReactions(hash=0))
        reactions: list[AvailableReaction] = reactions.reactions
        logger.info(f"Got {len(reactions)} reactions")

        for idx, reaction in enumerate(reactions):
            logger.info(f"Downloading reaction \"{reaction.title}\" (\"{reaction.reaction}\")")
            for sticker in (
                    reaction.static_icon, reaction.appear_animation, reaction.select_animation, reaction.center_icon,
                    reaction.activate_animation, reaction.effect_animation, reaction.around_animation,
            ):
                if sticker is None:
                    continue
                await download_reaction(client, idx, sticker, reactions_dir)

            with open(reactions_dir / f"{idx}.json", "w") as f:
                reaction_json = cast(dict[str, Any], TLObject.default(reaction))
                reaction_json["_index"] = idx
                json.dump(reaction_json, f, indent=4, default=TLObject.default, ensure_ascii=False)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
