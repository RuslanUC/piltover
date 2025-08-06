import json
from pathlib import Path


# Take emoji.json from https://github.com/carpedm20/emoji/blob/master/emoji/unicode_codes/emoji.json
#  and place it in the same directory with this script
def main() -> None:
    parent = Path(__file__).parent
    with open(parent / "emoji.json", "r", encoding="utf8") as f:
        emojis: dict[str, dict[str, int]] = json.load(f)

    with open("unicode_codes.py", "w") as f:
        f.write("EMOJIS = {\n")
        f.write("    ")
        f.write(", ".join(ascii(emoji) for emoji in emojis))
        f.write("\n")
        f.write("}\n")

        f.write("COMPONENTS = {\n")
        f.write("    ")
        f.write(", ".join(ascii(emoji) for emoji, data in emojis.items() if data["status"] == 1))
        f.write("\n")
        f.write("}\n")


if __name__ == "__main__":
    main()
