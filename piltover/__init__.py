import sys
from pathlib import Path

_current_dir = Path(__file__).parent
if (_current_dir / "tl_new.zip").exists():
    print("importing from zip")
    sys.path.insert(0, str((_current_dir / "tl_new.zip").absolute()))
    import tl_new
    sys.modules["piltover.tl_new"] = tl_new
    print("imported from zip")
