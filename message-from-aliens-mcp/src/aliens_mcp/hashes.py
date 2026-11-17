"""Connection-local opaque character identifiers."""

import zlib

from .errors import ValidationError

TOKEN_WIDTH = 4

TOKEN_SPACE = 36**TOKEN_WIDTH


def word_id(word: str, offset: int = 0) -> str:
    """Four-character CRC32/base36 candidate; GlyphIds resolves collisions."""

    value = (zlib.crc32(word.encode("utf-8")) + offset) % TOKEN_SPACE

    digits = []

    while value:
        value, remainder = divmod(value, 36)

        digits.append("0123456789abcdefghijklmnopqrstuvwxyz"[remainder])

    return ("".join(reversed(digits)) or "0").rjust(TOKEN_WIDTH, "0")


class GlyphIds:
    """Connection-local IDs, seeded with the sorted full vocabulary first.



    Linear probing resolves short-hash collisions without reassigning any ID.

    Catalogue IDs repeat across reconnects when the catalogue is unchanged;

    generated words are stable for the lifetime of this index.

    """

    def __init__(self) -> None:

        self.by_word: dict[str, str] = {}

        self.by_id: dict[str, str] = {}

    def register(self, words) -> None:

        for word in sorted(set(words)):
            if word in self.by_word:
                continue

            for offset in range(TOKEN_SPACE):
                token = word_id(word, offset)

                if token not in self.by_id:
                    self.by_word[word] = token

                    self.by_id[token] = word

                    break

            else:
                raise ValidationError("HASH_EXHAUSTED")
