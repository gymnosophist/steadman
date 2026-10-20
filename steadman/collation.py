"""Stable dictionary ordering for Latin and polytonic Greek headwords."""

from __future__ import annotations

import unicodedata


def alphabetical_key(text: str) -> tuple[str, str, str]:
    """Sort by letters of the headword, independently of its printed accents.

    Ignore case, combining marks (including breathing marks and iota subscripts),
    spaces, punctuation, and homonym numbers for primary order. Case folding
    gives final sigma the same position as medial sigma. Citation forms after
    a comma do not determine a word's primary position.

    Canonically equivalent Unicode spellings share a key; the complete NFC
    spelling breaks other ties deterministically without changing the display.
    This does not merge dictionary entries or change dictionary lookup keys.
    """
    canonical = unicodedata.normalize("NFC", text)
    headword = canonical.split(",", 1)[0]
    decomposed = unicodedata.normalize("NFD", headword)
    letters = "".join(char for char in decomposed if unicodedata.category(char) != "Mn").casefold()
    primary = "".join(char for char in letters if char.isalpha())
    return primary, canonical.casefold(), canonical
