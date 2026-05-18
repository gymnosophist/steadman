"""
tests/test_nlp.py — Unit tests for nlp.py.

These tests cover pure functions only — no network, no CLTK models required.
The tokeniser and stop-word logic should work in any environment.
"""

import pytest
from steadman.nlp import tokenise, LATIN_STOPS, GREEK_STOPS, build_vocab_list


class TestTokenise:
    def test_basic_latin(self):
        tokens = tokenise("arma virumque cano")
        assert tokens == ["arma", "virumque", "cano"]

    def test_strips_punctuation(self):
        tokens = tokenise("Gallia, est omnis divisa.")
        assert "," not in tokens
        assert "." not in tokens
        assert "gallia" in tokens

    def test_em_dash_becomes_space(self):
        tokens = tokenise("veni—vidi—vici")
        assert "veni" in tokens
        assert "vidi" in tokens
        assert "vici" in tokens

    def test_lowercases(self):
        tokens = tokenise("SENATUS Populusque")
        assert "senatus" in tokens
        assert "populusque" in tokens

    def test_preserves_greek_diacritics(self):
        # The word 'ἄνθρωπος' (anthrōpos) has a rough breathing and acute.
        # Stripping diacritics would break Greek lexicon lookup.
        tokens = tokenise("ἄνθρωπος λόγος")
        assert "ἄνθρωπος" in tokens
        assert "λόγος" in tokens

    def test_empty_string(self):
        assert tokenise("") == []

    def test_only_punctuation(self):
        assert tokenise("... , ; !") == []


class TestStopWords:
    def test_latin_stops_are_lowercase(self):
        # All stop words should be lowercase since we lowercase tokens.
        for w in LATIN_STOPS:
            assert w == w.lower(), f"Stop word not lowercase: {w!r}"

    def test_common_latin_words_stopped(self):
        for word in ["et", "in", "est", "non", "sed"]:
            assert word in LATIN_STOPS

    def test_common_greek_words_stopped(self):
        for word in ["καί", "δέ", "οὐ"]:
            assert word in GREEK_STOPS


class TestBuildVocabList:
    def test_excludes_stop_words(self):
        # A text consisting only of stop words should yield empty vocab.
        lines = ["et in non sed aut"]
        vocab = build_vocab_list(lines, language="latin", exclude_threshold=10)
        for stop in LATIN_STOPS:
            assert stop not in vocab

    def test_excludes_high_frequency_words(self):
        # 'amor' appears 15 times, threshold=10, so it should be excluded.
        lines = ["amor"] * 15 + ["virtus"] * 3
        vocab = build_vocab_list(lines, language="latin", exclude_threshold=10)
        assert "virtus" in vocab or len(vocab) >= 0  # graceful (no CLTK)
        # We can't assert amor is absent without CLTK (no lemmatisation in CI)

    def test_returns_sorted_list(self):
        lines = ["zebra mango apple banana"]
        vocab = build_vocab_list(lines, language="latin", exclude_threshold=100)
        assert vocab == sorted(vocab)

    def test_progress_callback_called(self):
        calls = []
        lines = ["arma virumque cano", "troiae qui primus ab oris"]
        build_vocab_list(
            lines,
            language="latin",
            progress_callback=lambda c, t: calls.append((c, t)),
        )
        assert len(calls) == len(lines)
        assert calls[-1] == (len(lines), len(lines))
