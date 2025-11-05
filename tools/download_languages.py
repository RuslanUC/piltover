import argparse
import json
import shutil
from asyncio import get_event_loop
from pathlib import Path
from types import SimpleNamespace

from loguru import logger
from pyrogram import Client
from pyrogram.raw.core import TLObject
from pyrogram.raw.functions.langpack import GetLanguages, GetLangPack
from pyrogram.raw.types import LangPackLanguage, LangPackDifference


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    platform: str
    data_dir: Path


async def extract_languages(client: Client, out_dir: Path, platform: str) -> None:
    platform_dir = out_dir / platform

    languages: list[LangPackLanguage] = await client.invoke(GetLanguages(lang_pack=platform))
    logger.info(f"Got {len(languages)} languages for platform \"{platform}\"")
    for language in languages:
        lang_dir = platform_dir / language.lang_code
        lang_dir.mkdir(parents=True, exist_ok=True)

        with open(lang_dir / "info.json", "w") as f:
            json.dump(language, f, indent=4, default=TLObject.default, ensure_ascii=False)

        diff: LangPackDifference = await client.invoke(GetLangPack(lang_pack=platform, lang_code=language.lang_code))
        logger.info(
            f"Got {len(diff.strings)} strings for language \"{language.lang_code}\" for platform \"{platform}\""
        )
        with open(lang_dir / "strings.json", "w") as f:
            json.dump(diff.strings, f, indent=4, default=TLObject.default, ensure_ascii=False)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-id", required=False, type=int, help="Telegram api id")
    parser.add_argument("--api-hash", required=False, type=str, help="Telegram api hash")
    parser.add_argument("--platform", type=str, help="Platform (e.g. android, tdesktop)", default="android")
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory to where languages will be download",
                        default=Path("./data").resolve())
    args = parser.parse_args(namespace=ArgsNamespace())

    out_dir = args.data_dir / "languages"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / args.platform).mkdir(parents=True, exist_ok=True)

    with open(out_dir / ".gitignore", "w") as f:
        f.write("*\n")

    async with Client(
            name="telegram", api_id=args.api_id, api_hash=args.api_hash, workdir=str(args.data_dir / "secrets"),
    ) as client:
        await extract_languages(client, out_dir, args.platform)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
