"""
Register the "Mini Pasha" star gift with upgrade variants.
Uses sqlite3 directly — no piltover.tl import needed.

Usage:
    PYTHONPATH=. .venv/bin/python tools/create_mini_pasha_gift.py \
        --base   /Volumes/C&A-Data/AnimatedStickerU.tgs \
        --var1   /Volumes/C&A-Data/AnimatedSticker1.tgs \
        --var2   /Volumes/C&A-Data/AnimatedSticker2.tgs \
        --var3   /Volumes/C&A-Data/AnimatedSticker3.tgs \
        --var4   /Volumes/C&A-Data/AnimatedSticker4.tgs \
        --craft1 /Volumes/C&A-Data/5.tgs \
        --craft2 /Volumes/C&A-Data/6.tgs \
        --craft3 /Volumes/C&A-Data/7.tgs \
        --craft4 /Volumes/C&A-Data/8.tgs
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Read DB path from system.toml (or env override)
def _db_path() -> Path:
    cfg_path = Path(os.environ.get("SYSTEM_CONFIG", "config/system.toml"))
    if cfg_path.exists():
        for line in cfg_path.read_text().splitlines():
            if "database_connection_string" in line and "sqlite" in line:
                # e.g.  database_connection_string = "sqlite://data/secrets/piltover.db"
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return Path(val.replace("sqlite://", ""))
    return Path("data/secrets/piltover.db")


def _random_long() -> int:
    return struct.unpack("<q", os.urandom(8))[0]


def _save_tgs(tgs_path: Path, data_dir: Path, cur: sqlite3.Cursor) -> int:
    raw  = tgs_path.read_bytes()
    fid  = uuid4()
    docs = data_dir / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    (data_dir / "photos").mkdir(parents=True, exist_ok=True)
    shutil.copy(tgs_path, docs / str(fid))

    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO file
            (physical_id, created_at, mime_type, size, type,
             constant_access_hash, constant_file_ref,
             photo_sizes, filename, sticker_alt, sticker_pos,
             supports_streaming, nosound, sticker_is_mask)
        VALUES (?, ?, 'application/x-tgsticker', ?, 5, ?, ?, '[]', ?, '🎁', 0, 0, 0, 0)
        """,
        (str(fid), now, len(raw), _random_long(), str(uuid4()), tgs_path.name),
    )
    return cur.lastrowid


def main(args: argparse.Namespace) -> None:
    db_path  = _db_path()
    data_dir = Path(os.environ.get("DATA_DIR", "data"))

    # Try to get data_dir from system.toml
    cfg_path = Path(os.environ.get("SYSTEM_CONFIG", "config/system.toml"))
    if cfg_path.exists():
        for line in cfg_path.read_text().splitlines():
            if "data_dir" in line and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                data_dir = Path(val)
                break

    print(f"DB:       {db_path}")
    print(f"Data dir: {data_dir}")

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    def save(label: str, path: str) -> int:
        print(f"  Saving {label}: {path}")
        fid = _save_tgs(Path(path), data_dir, cur)
        print(f"    → file id {fid}")
        return fid

    base_id     = save("base",    args.base)
    variant_ids = [save(f"var{i+1}",   getattr(args, f"var{i+1}"))    for i in range(4)]
    craft_ids   = [save(f"craft{i+1}", getattr(args, f"craft{i+1}"))  for i in range(4)]

    con.commit()
    con.close()

    out = Path("data/mini_pasha_gift.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "base_file_id":     base_id,
        "variant_file_ids": variant_ids,
        "craft_file_ids":   craft_ids,
    }, indent=2))
    print(f"\nDone → {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base",   required=True)
    p.add_argument("--var1",   required=True)
    p.add_argument("--var2",   required=True)
    p.add_argument("--var3",   required=True)
    p.add_argument("--var4",   required=True)
    p.add_argument("--craft1", required=True)
    p.add_argument("--craft2", required=True)
    p.add_argument("--craft3", required=True)
    p.add_argument("--craft4", required=True)
    main(p.parse_args())
