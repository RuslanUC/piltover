import os
from compileall import compile_dir
from shutil import copy
from pathlib import Path

SRC = Path("piltover/tl_new_c")
DST = Path("piltover/tl_new_compiled")
copied = set()


def copy_compiled(path: Path) -> None:
    for _, dirs, _ in os.walk(path):
        for d in dirs:
            if d == "__pycache__" and path not in copied:
                out = DST / path.relative_to(SRC)
                out.mkdir(parents=True, exist_ok=True)
                #(out / "__pycache__").mkdir(parents=True, exist_ok=True)
                print(f"{path} -> {out}")
                for file in os.listdir(path / "__pycache__"):
                    if not file.endswith(".pyc"):
                        continue
                    copy(path / "__pycache__" / file, out / f"{file.split('.')[0]}.pyc")
                    #copy(path / "__pycache__" / file, out / "__pycache__" / file)
                copied.add(path)
            else:
                copy_compiled(path / d)


def main() -> None:
    compile_dir(SRC, quiet=True, optimize=2)
    copy_compiled(SRC)


if __name__ == '__main__':
    main()
