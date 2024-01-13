from pathlib import Path

root_dir = Path(__file__).parent.parent.parent.resolve(strict=True)
files_dir = root_dir / "data" / "files"
files_dir.mkdir(parents=True, exist_ok=True)
(files_dir / "parts").mkdir(parents=True, exist_ok=True)
