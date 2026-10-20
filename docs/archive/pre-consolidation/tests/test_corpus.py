"""
tests/test_corpus.py — Unit tests for corpus.py.

We test the pure functions (chunk_lines) here.
Network-dependent functions (fetch_catalog, fetch_text) are not tested
in this suite — they belong in integration tests that require network access.
"""

import pytest
from steadman.corpus import chunk_lines


class TestChunkLines:
    LINES = [f"line {i}" for i in range(100)]

    def test_poetry_chunk_size(self):
        chunks = list(chunk_lines(self.LINES, chunk_size=20, mode="poetry"))
        assert len(chunks) == 5  # 100 lines / 20 per chunk
        assert chunks[0].count("\n") == 19  # 20 lines = 19 newlines

    def test_poetry_last_chunk_smaller(self):
        lines = [f"line {i}" for i in range(45)]
        chunks = list(chunk_lines(lines, chunk_size=20, mode="poetry"))
        assert len(chunks) == 3
        # Last chunk has 5 lines (45 - 20 - 20)
        assert chunks[-1].count("\n") == 4

    def test_prose_chunk_by_words(self):
        # 100 lines, each "line N" = 2 words = 200 words total
        chunks = list(chunk_lines(self.LINES, chunk_size=50, mode="prose"))
        assert len(chunks) == 4  # 200 words / 50 per chunk

    def test_prose_joins_lines(self):
        lines = ["hello world", "foo bar"]
        chunks = list(chunk_lines(lines, chunk_size=10, mode="prose"))
        assert len(chunks) == 1
        assert "hello world foo bar" == chunks[0]

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            list(chunk_lines(self.LINES, chunk_size=20, mode="hexameter"))

    def test_empty_lines(self):
        chunks = list(chunk_lines([], chunk_size=20, mode="poetry"))
        assert chunks == []
