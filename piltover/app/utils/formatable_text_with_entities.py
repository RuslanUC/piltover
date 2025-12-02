from collections import defaultdict
from typing import Any

from piltover.tl import MessageEntityBold, MessageEntityItalic, MessageEntityUnderline, MessageEntityStrike, \
    MessageEntitySpoiler, MessageEntityCode, MessageEntityPre, MessageEntityUrl, MessageEntityBotCommand, \
    MessageEntityMention

BOLD_DELIM = "**"
ITALIC_DELIM = "__"
UNDERLINE_DELIM = "--"
STRIKE_DELIM = "~~"
SPOILER_DELIM = "||"
CODE_DELIM = "`"
PRE_DELIM = "```"
URL_START = "<a>"
URL_END = "</a>"
COMMAND_START = "<c>"
COMMAND_END = "</c>"
USERNAME_START = "<u>"
USERNAME_END = "</u>"

DELIMS = [
    (BOLD_DELIM, BOLD_DELIM),
    (ITALIC_DELIM, ITALIC_DELIM),
    (UNDERLINE_DELIM, UNDERLINE_DELIM),
    (STRIKE_DELIM, STRIKE_DELIM),
    (SPOILER_DELIM, SPOILER_DELIM),
    #(PRE_DELIM, PRE_DELIM),
    (CODE_DELIM, CODE_DELIM),
    (URL_START, URL_END),
    (COMMAND_START, COMMAND_END),
    (USERNAME_START, USERNAME_END),
]
TYPES = {
    BOLD_DELIM: MessageEntityBold.tlid(),
    ITALIC_DELIM: MessageEntityItalic.tlid(),
    UNDERLINE_DELIM: MessageEntityUnderline.tlid(),
    STRIKE_DELIM: MessageEntityStrike.tlid(),
    SPOILER_DELIM: MessageEntitySpoiler.tlid(),
    CODE_DELIM: MessageEntityCode.tlid(),
    PRE_DELIM: MessageEntityPre.tlid(),
    URL_START: MessageEntityUrl.tlid(),
    COMMAND_START: MessageEntityBotCommand.tlid(),
    USERNAME_START: MessageEntityMention.tlid(),
}


class Entity:
    def __init__(
            self, type_: int, offset: int, length: int, offset_depends: dict[str, int], length_depends: dict[str, int],
    ) -> None:
        self.type = type_
        self.offset = offset
        self.length = length
        self.offset_depends = offset_depends
        self.length_depends = length_depends

    def format(self, fmt_options: dict[str, Any]) -> dict[str, str | int]:
        if not self.offset_depends and not self.length_depends:
            return {
                "_": self.type,
                "offset": self.offset,
                "length": self.length,
            }

        add_offset = sum(
            len(fmt_options[fmt_name]) * count - (len(fmt_name) + 2) * count
            for fmt_name, count in self.offset_depends.items()
        )
        add_length = sum(
            len(fmt_options[fmt_name]) * count - (len(fmt_name) + 2) * count
            for fmt_name, count in self.length_depends.items()
        )

        return {
            "_": self.type,
            "offset": self.offset + add_offset,
            "length": self.length + add_length,
        }


class FormatableTextWithEntities:
    def __init__(self, text: str) -> None:
        self._text = ""
        self._entities: list[Entity] = []
        self._parse_entities(text)

    def _parse_entities(self, text: str) -> None:
        result_text = ""
        depends_on = defaultdict(lambda: 0)

        pos = 0
        while pos < len(text):
            if text[pos] == "{" and pos + 1 < len(text):
                end_curly_pos = text.index("}", pos)
                fmt_name = text[pos + 1:end_curly_pos]
                depends_on[fmt_name] += 1
                result_text += f"{{{fmt_name}}}"
                pos = end_curly_pos + 1
                continue

            got_delim = need_delim = None
            for delim, delim_end in DELIMS:
                if delim != delim_end:
                    if text.startswith(delim, pos):
                        got_delim = delim
                        need_delim = delim_end
                        pos += len(delim)
                        break
                    continue

                dchar = delim[0]
                dlen = len(delim)
                if text[pos] == dchar and pos + dlen - 1 < len(text) and text[pos + dlen - 1] == dchar:
                    got_delim = need_delim = delim
                    pos += dlen
                    break

            if got_delim is None or need_delim is None:
                result_text += text[pos]
                pos += 1
                continue

            try:
                end_pos = text.index(need_delim, pos)
            except ValueError:
                result_text += got_delim
                pos += 1
                continue

            offset_depends = depends_on.copy()
            length_depends = defaultdict(lambda: 0)
            curly_start = pos
            while True:
                try:
                    start_curly = text.index("{", curly_start, end_pos)
                    end_curly = curly_start = text.index("}", start_curly, end_pos)
                except ValueError:
                    break

                fmt_name = text[start_curly + 1:end_curly]
                depends_on[fmt_name] += 1
                length_depends[fmt_name] += 1

            self._entities.append(Entity(
                type_=TYPES[got_delim],
                offset=len(result_text),
                length=end_pos - pos,
                offset_depends=offset_depends,
                length_depends=length_depends,
            ))

            result_text += text[pos:end_pos]
            pos = end_pos + len(need_delim)

        self._text = result_text

    def format(self, **kwargs) -> tuple[str, list[dict[str, str | int]]]:
        kwargs = {name: str(val) for name, val in kwargs.items()}
        return self._text.format(**kwargs), [entity.format(kwargs) for entity in self._entities]


def _test() -> None:
    text = (
        "This is **some** text __with__ entities, "
        "url (<a>https://example.com</a>) "
        "and {fmt} --formatting-- `options ({opts})`."
    )

    ftwe = FormatableTextWithEntities(text)
    formatted, entities = ftwe.format(fmt=2, opts="\"fmt\" and \"opts\"")
    print(formatted)
    print(entities)

    for entity in entities:
        print(f"entity \"{entity['_']}\": {formatted[entity['offset']:entity['offset']+entity['length']]}")


if __name__ == "__main__":
    _test()
