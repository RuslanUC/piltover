# Mini Pasha Star Gift Setup Guide

## Problem
`piltover/tl/functions/_root.py` line 257 has `class True(...)` which is invalid Python 3.11 syntax.

## Solution: Use Compiled .pyc Only

### Step 1: Create Working .pyc
```bash
cd /Volumes/C&A-Data/piltover

# Patch _root.py to make it compilable
python3 << 'EOF'
src = open('piltover/tl/functions/_root.py').read()
patched = src.replace(
    'class True(TLRequest[tl.base.True]):',
    'class True_(TLRequest[bool]):'
).replace('tl.base.True', 'bool')
open('/tmp/_root_patched.py', 'w').write(patched)
EOF

# Backup original
cp piltover/tl/functions/_root.py /tmp/_root_real.py

# Compile patched version to .pyc
cp /tmp/_root_patched.py piltover/tl/functions/_root.py
.venv/bin/python -m py_compile piltover/tl/functions/_root.py

# Restore original (Python will use .pyc)
cp /tmp/_root_real.py piltover/tl/functions/_root.py
```

### Step 2: Initialize Database
```bash
cd /Volumes/C&A-Data/piltover

mkdir -p data/secrets

PYTHONPATH=. APP_CONFIG=config/app.toml GATEWAY_CONFIG=config/gateway.toml \
SYSTEM_CONFIG=config/system.toml WORKER_CONFIG=config/worker.toml \
.venv/bin/python -c "
import asyncio
from tortoise import Tortoise
from piltover.config import TORTOISE_ORM
async def run():
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
    await Tortoise.close_connections()
asyncio.run(run())
"
```

### Step 3: Register Gift Files
```bash
cd /Volumes/C&A-Data/piltover

python3 tools/create_mini_pasha_gift.py \
  --base   "/Volumes/C&A-Data/AnimatedStickerU.tgs" \
  --var1   "/Volumes/C&A-Data/AnimatedSticker1.tgs" \
  --var2   "/Volumes/C&A-Data/AnimatedSticker2.tgs" \
  --var3   "/Volumes/C&A-Data/AnimatedSticker3.tgs" \
  --var4   "/Volumes/C&A-Data/AnimatedSticker4.tgs" \
  --craft1 "/Volumes/C&A-Data/5.tgs" \
  --craft2 "/Volumes/C&A-Data/6.tgs" \
  --craft3 "/Volumes/C&A-Data/7.tgs" \
  --craft4 "/Volumes/C&A-Data/8.tgs"
```

### Step 4: Verify
- Check `data/mini_pasha_gift.json` exists with file IDs
- Check `data/documents/` has 8 TGS files with UUIDs
- Check `data/secrets/piltover.db` exists

## Key Files
- `piltover/app/handlers/payments.py` — Gift handlers (GetStarGifts, CraftStarGift)
- `piltover/db/models/user.py` — Added `stars` field
- `piltover/db/migrations/0040_auto_20260518_stars.py` — Migration
- `piltover/app/handlers/auth.py` — New users get 10000 stars
- `tools/create_mini_pasha_gift.py` — Gift registration script
- `data/mini_pasha_gift.json` — Generated file IDs mapping

## Constants
- `MINI_PASHA_GIFT_ID = 1_000_001`
- `MINI_PASHA_STARS = 410` (base cost)
- `MINI_PASHA_UPGRADE = 1000` (upgrade cost)
- `CRAFT_CHANCE_EACH = 0.25` (25% per variant)

## Testing
```bash
# Start server
cd /Volumes/C&A-Data/piltover
poetry run python -m piltover.app.app

# In another terminal, test endpoints:
# GetStarGifts, GetStarGiftUpgradePreview, CraftStarGift
```
