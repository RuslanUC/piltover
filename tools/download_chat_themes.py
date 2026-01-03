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
from pyrogram.raw.functions.account import GetChatThemes
from pyrogram.raw.types import Theme, ThemeSettings, WallPaper
from pyrogram.raw.types.account import Themes

from download_utils import download_document


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    data_dir: Path


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
