import argparse
import json
import shutil
from asyncio import get_event_loop
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from loguru import logger
from pyrogram import Client
from pyrogram.raw.core import TLObject
from pyrogram.raw.functions.messages import GetAvailableReactions
from pyrogram.raw.types import AvailableReaction
from pyrogram.raw.types.messages import AvailableReactions

from download_utils import download_document


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    data_dir: Path


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

    with open(reactions_dir / ".gitignore", "w") as f:
        f.write("*\n")

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
                await download_document(client, idx, sticker, reactions_dir)

            with open(reactions_dir / f"{idx}.json", "w") as f:
                reaction_json = cast(dict[str, Any], TLObject.default(reaction))
                reaction_json["_index"] = idx
                json.dump(reaction_json, f, indent=4, default=TLObject.default, ensure_ascii=False)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
