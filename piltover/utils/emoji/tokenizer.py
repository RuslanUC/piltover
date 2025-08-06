"""
emoji.tokenizer
~~~~~~~~~~~~~~~

Components for detecting and tokenizing emoji in strings.

"""

from typing import NamedTuple, Iterator, Any
from .unicode_codes import EMOJIS, COMPONENTS


__all__ = [
    'Token',
    'tokenize',
]

ZWJ = '\u200d'
_SEARCH_TREE: dict[str, Any] = {}


class Token(NamedTuple):
    chars: str
    is_emoji: bool
    is_zwj: bool


STATUS_COMPONENT = 1


def tokenize(string: str) -> Iterator[Token]:
    """
    Finds unicode emoji in a string. Yields all normal characters as a named
    tuple :class:`Token`.

    :param string: String contains unicode characters. MUST BE UNICODE.
    :return: An iterable of tuples :class:`Token`
    """

    tree = get_search_tree()
    result: list[Token] = []
    i = 0
    length = len(string)
    ignore: list[int] = []  # index of chars in string that are skipped, i.e. the ZWJ-char in non-RGI-ZWJ-sequences
    while i < length:
        consumed = False
        char = string[i]
        if i in ignore:
            i += 1
            if char == ZWJ:
                result.append(Token(char, False, True))
            continue

        elif char in tree:
            j = i + 1
            sub_tree = tree[char]
            while j < length and string[j] in sub_tree:
                if j in ignore:
                    break
                sub_tree = sub_tree[string[j]]
                j += 1
            if 'has_data' in sub_tree:
                code_points = string[i:j]

                # We cannot yield the result here, we need to defer
                # the call until we are sure that the emoji is finished
                # i.e. we're not inside an ongoing ZWJ-sequence

                i = j - 1
                consumed = True
                result.append(Token(code_points, True, False))

        elif (
                char == ZWJ
                and result
                and result[-1].chars in EMOJIS
                and i > 0
                and string[i - 1] in tree
        ):
            # the current char is ZWJ and the last match was an emoji
            ignore.append(i)
            if result[-1].chars in COMPONENTS:
                # last match was a component, it could be ZWJ+EMOJI+COMPONENT
                # or ZWJ+COMPONENT
                i = i - sum(len(t.chars) for t in result[-2:])
                if string[i] == ZWJ:
                    # It's ZWJ+COMPONENT, move one back
                    i += 1
                    del result[-1]
                else:
                    # It's ZWJ+EMOJI+COMPONENT, move two back
                    del result[-2:]
            else:
                # last match result[-1] was a normal emoji, move cursor
                # before the emoji
                i = i - len(result[-1].chars)
                del result[-1]
            continue

        elif result:
            yield from result
            result = []

        if not consumed and char != '\ufe0e' and char != '\ufe0f':
            result.append(Token(char, False, char == ZWJ))
        i += 1

    yield from result


def get_search_tree() -> dict[str, Any]:
    if not _SEARCH_TREE:
        for emj in EMOJIS:
            sub_tree = _SEARCH_TREE
            lastidx = len(emj) - 1
            for i, char in enumerate(emj):
                if char not in sub_tree:
                    sub_tree[char] = {}
                sub_tree = sub_tree[char]
                if i == lastidx:
                    sub_tree['has_data'] = True
    return _SEARCH_TREE