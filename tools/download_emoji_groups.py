import argparse
import json
import shutil
from asyncio import get_event_loop
from pathlib import Path
from types import SimpleNamespace

from loguru import logger
from pyrogram import Client
from pyrogram.raw.core import TLObject
from pyrogram.raw.functions.messages import GetEmojiGroups, GetEmojiStatusGroups, GetEmojiProfilePhotoGroups

from tests._emoji_groups_compat import GetEmojiStickerGroupsCompat, EmojiGroupGreetingCompat, EmojiGroupPremiumCompat

GROUPS = [
    ("sticker_groups", GetEmojiStickerGroupsCompat(hash=0)),
    ("groups", GetEmojiGroups(hash=0)),
    ("status_groups", GetEmojiStatusGroups(hash=0)),
    ("profile_photo_groups", GetEmojiProfilePhotoGroups(hash=0)),
]


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    data_dir: Path


async def extract_emoji_groups(client: Client, out_dir: Path) -> None:
    from pyrogram.raw import all as pyrogram_all

    classes = (
        EmojiGroupGreetingCompat,
        EmojiGroupPremiumCompat,
    )

    for cls in classes:
        pyrogram_all.objects[cls.tlid()] = cls

    for name, req in GROUPS:
        groups = await client.invoke(req)
        logger.success(f"Got emoji group {name!r}")
        with open(out_dir / f"{name}.json", "w") as f:
            json.dump(groups, f, indent=4, default=TLObject.default, ensure_ascii=False)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-id", required=False, type=int, help="Telegram api id")
    parser.add_argument("--api-hash", required=False, type=str, help="Telegram api hash")
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory to where emoji groups will be download",
                        default=Path("./data").resolve())
    args = parser.parse_args(namespace=ArgsNamespace())

    out_dir = args.data_dir / "emoji_groups"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / ".gitignore", "w") as f:
        f.write("*\n")

    async with Client(
            name="telegram", api_id=args.api_id, api_hash=args.api_hash, workdir=str(args.data_dir / "secrets"),
    ) as client:
        await extract_emoji_groups(client, out_dir)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
