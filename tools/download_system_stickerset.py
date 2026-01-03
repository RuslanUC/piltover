import argparse
import json
import shutil
from asyncio import get_event_loop
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from loguru import logger
from pyrogram import Client
from pyrogram.raw.core import TLObject
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.types import InputStickerSetID, InputStickerSetAnimatedEmoji, \
    InputStickerSetDice, InputStickerSetAnimatedEmojiAnimations, InputStickerSetEmojiGenericAnimations, \
    InputStickerSetEmojiDefaultStatuses, InputStickerSetEmojiDefaultTopicIcons, Document
from pyrogram.raw.types.messages import StickerSet as MessagesStickerSet

from download_utils import download_document, ClientCachedMediaSessions

InputStickerSet = InputStickerSetID | InputStickerSetAnimatedEmoji | InputStickerSetDice \
                  | InputStickerSetAnimatedEmojiAnimations | InputStickerSetEmojiGenericAnimations \
                  | InputStickerSetEmojiDefaultStatuses | InputStickerSetEmojiDefaultTopicIcons


to_download = [
    ("animated_emoji", InputStickerSetAnimatedEmoji()),
    ("dice_basketball", InputStickerSetDice(emoticon="🏀")),
    ("dice_die", InputStickerSetDice(emoticon="🎲")),
    ("dice_target", InputStickerSetDice(emoticon="🎯")),
    ("emoji_animations", InputStickerSetAnimatedEmojiAnimations()),
    ("generic_animations", InputStickerSetEmojiGenericAnimations()),
    ("user_statuses", InputStickerSetEmojiDefaultStatuses()),
    ("topic_icons", InputStickerSetEmojiDefaultTopicIcons()),
]


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    data_dir: Path


async def download_stickerset(client: Client, out_dir: Path, stickerset: InputStickerSet, set_type: str) -> None:
    sticker_set: MessagesStickerSet = await client.invoke(GetStickerSet(stickerset=stickerset, hash=0))
    logger.success(f"Got {len(sticker_set.documents)} stickers for stickerset {set_type!r}")
    for idx, doc in enumerate(cast(list[Document], sticker_set.documents)):
        logger.info(f"Downloading sticker {doc.id}")
        await download_document(client, idx, doc, out_dir)

    with open(out_dir / f"set.json", "w") as f:
        json.dump(sticker_set, f, indent=4, default=TLObject.default, ensure_ascii=False)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-id", required=False, type=int, help="Telegram api id")
    parser.add_argument("--api-hash", required=False, type=str, help="Telegram api hash")
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory to where chat themes will be download",
                        default=Path("./data").resolve())
    args = parser.parse_args(namespace=ArgsNamespace())

    out_dir = args.data_dir / "stickersets"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / ".gitignore", "w") as f:
        f.write("*\n")

    async with ClientCachedMediaSessions(
            name="telegram", api_id=args.api_id, api_hash=args.api_hash, workdir=str(args.data_dir / "secrets"),
    ) as client:
        for set_type, input_set in to_download:
            set_out_dir = out_dir / set_type
            set_out_dir.mkdir(parents=True, exist_ok=True)
            await download_stickerset(client, set_out_dir, input_set, set_type)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
