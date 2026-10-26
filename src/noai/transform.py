"""Deterministic text substitution without reserializing the HTML document.

The parser identifies editable source spans. Edits are assembled in source order so all
untouched source, including tag spelling and whitespace, stays byte-for-byte
identical after UTF-8 encoding. Template expressions are masked before parsing.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
import hashlib
import html
import re
from html.parser import HTMLParser

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_ENTITY = re.compile(r"&(?:#[xX][0-9a-fA-F]+|#[0-9]+|[A-Za-z][A-Za-z0-9]+);")
_TEMPLATE = re.compile(r"{{.*?}}|{%.*?%}|{#.*?#}|<%.*?%>", re.DOTALL)
_ATTRIBUTE = re.compile(
    r'''([^\s/>=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?'''
)
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_CODE = frozenset("script style pre code kbd samp svg math".split())
_TEXT_ATTRIBUTES = frozenset({"alt", "title", "placeholder", "aria-label", "aria-description"})
_META_TEXT = frozenset({
    "description", "keywords", "author", "og:title", "og:description",
    "og:site_name", "twitter:title", "twitter:description", "twitter:image:alt",
    "og:image:alt",
})


def _word(word: str, seed: str) -> str:
    """Use an unambiguous, versioned hash preimage for each character."""
    prefix = b"noai-set-v1\0" + seed.encode("utf-8") + b"\0" + word.lower().encode("utf-8")
    result = []
    for index, character in enumerate(word):
        digest = hashlib.sha256(prefix + b"\0" + str(index).encode("ascii")).digest()
        number = int.from_bytes(digest, "big")
        if character.isascii() and character.isalpha():
            base = ord("A" if character.isupper() else "a")
            result.append(chr(base + (ord(character) - base + 1 + number % 25) % 26))
        elif character.isdecimal() and character.isascii():
            result.append(str((int(character) + 1 + number % 9) % 10))
        elif character.isalpha() or character.isnumeric():
            # Unicode letters/numbers become ASCII; punctuation remains intact.
            base = ord("A" if character.isupper() else "a")
            result.append(chr(base + number % 26))
        else:
            result.append(character)
    return "".join(result)


def garble_text(text: str, seed: str = "sovereignty") -> str:
    """Scramble Unicode words; preserve whitespace, punctuation and case shape.

    This is deterministic substitution, not encryption or a training defense.
    """
    return _WORD.sub(lambda match: _word(match[0], seed), text)


def _garble_fragment(fragment: str, seed: str) -> str:
    """Keep entity syntax unless the entity itself encodes readable text."""
    parts = []
    position = 0
    for match in _ENTITY.finditer(fragment):
        parts.append(garble_text(fragment[position:match.start()], seed))
        decoded = html.unescape(match[0])
        changed = garble_text(decoded, seed)
        parts.append(html.escape(changed, quote=True) if decoded != match[0] and changed != decoded else match[0])
        position = match.end()
    parts.append(garble_text(fragment[position:], seed))
    return "".join(parts)


class _SpanCollector(HTMLParser):
    """Collect replacements while retaining source offsets and nesting context."""

    def __init__(self, source: str, seed: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.seed = seed
        self.edits: list[tuple[int, int, str]] = []
        self.stack: list[tuple[str, bool]] = []
        self.lines = [0] + [match.end() for match in re.finditer("\n", source)]
        self.protected = [(m.start(), m.end()) for m in _TEMPLATE.finditer(source)]
        self.protected_starts = [start for start, _ in self.protected]
        self.protected_ends = [end for _, end in self.protected]

    def source_offset(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def blocked(self) -> bool:
        return bool(self.stack and self.stack[-1][1])

    def replace(self, start: int, end: int) -> None:
        """Subtract protected template spans before transforming source text."""
        cursor = start
        first = bisect_right(self.protected_ends, start)
        last = bisect_left(self.protected_starts, end)
        for left, right in self.protected[first:last]:
            self._edit(cursor, min(left, end))
            cursor = min(end, right)
        self._edit(cursor, end)

    def _edit(self, start: int, end: int) -> None:
        if start < end:
            original = self.source[start:end]
            replacement = _garble_fragment(original, self.seed)
            if replacement != original:
                self.edits.append((start, end, replacement))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        blocked = self.blocked() or tag in _CODE or "data-noai" in values
        if not blocked:
            raw = self.get_starttag_text()
            assert raw is not None
            # Skip the opening '<tag'; scan attributes without matching inside values.
            name = re.match(r"<[^\s/>]+", raw)
            assert name is not None
            for match in _ATTRIBUTE.finditer(raw, name.end()):
                attribute = match[1].lower()
                is_meta = (
                    tag == "meta" and attribute == "content"
                    and (values.get("name") or values.get("property") or "").lower() in _META_TEXT
                )
                if attribute in _TEXT_ATTRIBUTES or is_meta:
                    group = next((i for i in (2, 3, 4) if match[i] is not None), None)
                    if group is not None:
                        self.replace(self.source_offset() + match.start(group), self.source_offset() + match.end(group))
        if tag not in _VOID:
            self.stack.append((tag, blocked))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if not self.blocked():
            self.replace(self.source_offset(), self.source_offset() + len(data))

    def handle_entityref(self, name: str) -> None:
        self._entity(name)

    def handle_charref(self, name: str) -> None:
        self._entity("#" + name)

    def _entity(self, name: str) -> None:
        if not self.blocked():
            start = self.source_offset()
            end = start + len(name) + 1
            if self.source[end:end + 1] == ";":
                end += 1
            raw = self.source[start:end]
            decoded = html.unescape(raw)
            transformed = garble_text(decoded, self.seed)
            if decoded != raw and transformed != decoded:
                self.edits.append((start, end, html.escape(transformed, quote=True)))


def garble_html(source: str, seed: str = "sovereignty") -> str:
    """Garble HTML text and descriptive attributes, preserving code and markup.

    Basic {{…}}, {%…%}, {#…#} and <%…%> template expressions are preserved.
    This is an HTML source transformer, not a browser or a template compiler.
    """
    parser = _SpanCollector(source, seed)
    masked = _TEMPLATE.sub(lambda m: "".join("\n" if c == "\n" else "x" for c in m[0]), source)
    parser.feed(masked)
    parser.close()
    parts = []
    cursor = 0
    for start, end, replacement in sorted(parser.edits):
        parts.extend((source[cursor:start], replacement))
        cursor = end
    parts.append(source[cursor:])
    return "".join(parts)
