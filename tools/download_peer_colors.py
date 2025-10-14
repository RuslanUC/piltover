import argparse
import json
import shutil
from array import array
from asyncio import get_event_loop
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from loguru import logger
from pyrogram import Client

from piltover.tl.types.help import PeerColors
from tests._peer_colors_compat import GetPeerColorsCompat, PeerColorsCompat, PeerColorOptionCompat, \
    PeerColorOption_167Compat, PeerColorSetCompat, PeerColorProfileSetCompat, GetPeerProfileColorsCompat


class ArgsNamespace(SimpleNamespace):
    api_id: int
    api_hash: str
    data_dir: Path


def TLObject_default(obj: Any) -> str | dict[str, str] | list:
    if isinstance(obj, bytes):
        return repr(obj)
    if isinstance(obj, array):
        return list(obj)

    return {
        "_": obj.QUALNAME,
        **{
            attr: getattr(obj, attr)
            for attr in obj.__slots__
            if getattr(obj, attr) is not None
        }
    }


async def extract_peer_colors(client: Client, out_dir: Path) -> None:
    from pyrogram.raw import all as pyrogram_all
    from piltover.tl import all as piltover_all

    classes = (
            GetPeerColorsCompat,
            GetPeerProfileColorsCompat,
            PeerColorsCompat,
            PeerColorOptionCompat,
            PeerColorOption_167Compat,
            PeerColorSetCompat,
            PeerColorProfileSetCompat,
    )

    for cls in classes:
        pyrogram_all.objects[cls.tlid()] = piltover_all.objects[cls.tlid()] = cls

    colors: PeerColors = await client.invoke(GetPeerColorsCompat(hash=0))
    logger.info(f"Got {len(colors.colors)} peer colors")
    for idx, color in enumerate(colors.colors):
        if color.color_id <= 6 or not color.colors:
            continue

        logger.info(f"Saving accent color \"{color.color_id}\"")
        with open(out_dir / "accent" / f"{idx}.json", "w") as f:
            json.dump(color, f, indent=4, default=TLObject_default, ensure_ascii=False)

    colors: PeerColors = await client.invoke(GetPeerProfileColorsCompat(hash=0))
    logger.info(f"Got {len(colors.colors)} peer colors")
    for idx, color in enumerate(colors.colors):
        logger.info(f"Saving profile color \"{color.color_id}\"")
        with open(out_dir / "profile" / f"{idx}.json", "w") as f:
            json.dump(color, f, indent=4, default=TLObject_default, ensure_ascii=False)

    for cls in classes:
        piltover_all.objects[cls.tlid()] = cls.RESTORE_CLS


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-id", required=False, type=int, help="Telegram api id")
    parser.add_argument("--api-hash", required=False, type=str, help="Telegram api hash")
    parser.add_argument("--data-dir", type=Path,
                        help="Path to data directory to where peer colors will be download",
                        default=Path("./data").resolve())
    args = parser.parse_args(namespace=ArgsNamespace())

    out_dir = args.data_dir / "peer_colors"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "accent").mkdir(parents=True, exist_ok=True)
    (out_dir / "profile").mkdir(parents=True, exist_ok=True)

    with open(out_dir / ".gitignore", "w") as f:
        f.write("*\n")

    async with Client(
            name="telegram", api_id=args.api_id, api_hash=args.api_hash, workdir=str(args.data_dir / "secrets"),
    ) as client:
        await extract_peer_colors(client, out_dir)


if __name__ == "__main__":
    get_event_loop().run_until_complete(main())
