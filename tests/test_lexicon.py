"""Unit tests for the pure helper functions in steadman.lexicon.

These need no network access or third-party lexicon data.
"""

from steadman.lexicon import (
    _GREEK_OVERRIDES,
    _looks_like_stranded_note,
    _strip_accents,
)


def test_strip_accents_removes_polytonic_marks():
    assert _strip_accents("ἀγαθός") == "αγαθος"
    assert _strip_accents("πᾶς") == "πας"


def test_strip_accents_leaves_plain_letters_alone():
    assert _strip_accents("λογος") == "λογος"


def test_stranded_note_detected():
    # Real lsj9 corruption: the gloss for πολύς is a dialect note.
    assert _looks_like_stranded_note("Att. gen. dat")
    assert _looks_like_stranded_note("")


def test_real_gloss_not_flagged():
    assert not _looks_like_stranded_note("much, many")


def test_overrides_are_real_glosses():
    # An override must never itself look like a stranded note.
    for headword, gloss in _GREEK_OVERRIDES.items():
        assert not _looks_like_stranded_note(gloss), headword
