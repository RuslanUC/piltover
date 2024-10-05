import sys
from pathlib import Path
from time import time

from loguru import logger

_current_dir = Path(__file__).parent
if (_current_dir / "tl.zip").exists():
    logger.debug("Importing tl from zip...")
    start_time = time()

    sys.path.insert(0, str((_current_dir / "tl.zip").absolute()))
    import tl
    sys.modules["piltover.tl"] = tl

    logger.debug(f"Importing tl from zip took {time() - start_time:.2f} seconds.")
    start_time = time()

    add_modules = {}
    for mod_name, mod in sys.modules.items():
        if not mod_name.startswith("tl"):
            continue
        add_modules[f"piltover.{mod_name}"] = mod
    sys.modules.update(add_modules)

    logger.debug(f"Adding tl from zip to sys.modules under {__name__} module took {time() - start_time:.3f} seconds.")
