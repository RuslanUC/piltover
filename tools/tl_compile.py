import os
from compileall import compile_dir
from shutil import copy
from pathlib import Path
from zipfile import ZipFile, Path as ZipPath

SRC = Path("piltover/tl_new_c")
copied = set()
out_zip = ZipFile("piltover/tl_new.zip", "w")
out_zip.mkdir("tl_new")


def copy_compiled(path: Path) -> None:
    for _, dirs, _ in os.walk(path):
        for d in dirs:
            if d == "__pycache__" and path not in copied:
                out = f"tl_new/{path.relative_to(SRC)}"
                if out == "tl_new/.":
                    out = "tl_new"

                print(f"{path}...")
                for file in os.listdir(path / "__pycache__"):
                    if not file.endswith(".pyc"):
                        continue
                    with open(path / "__pycache__" / file, "rb") as f:
                        out_zip.writestr(f"{out}/{file.split('.')[0]}.pyc", f.read())

                copied.add(path)
            else:
                copy_compiled(path / d)


def main() -> None:
    compile_dir(SRC, quiet=True, optimize=2)
    copy_compiled(SRC)


if __name__ == '__main__':
    main()
