"""
corpus.py — Text retrieval and catalog management.

This module separates all corpus concerns from NLP and rendering.
Two sources are supported:

  1. Tesserae (Latin + Greek) — accessed via the public REST API.
     Endpoint: https://tesserae.caset.buffalo.edu/texts/
     This replaces the old CSV catalogs and the cltkreaders dependency.

  2. Perseus/SCAIFE — used as a fallback for metadata enrichment.
     Endpoint: https://scaife.perseus.org/api/

Why Tesserae over the Latin Library?
  The Latin Library is a great resource but its texts are HTML pages
  requiring scraping (fragile). Tesserae ships clean, tokenised plain
  text with Locus-based line keys — exactly what we need.
"""

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Iterator
from pathlib import Path

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tesserae REST API
# ---------------------------------------------------------------------------

TESSERAE_API = "https://tesserae.caset.buffalo.edu/texts" # removed trailing slash 

# Language slugs as Tesserae understands them.
# slight edits to lang_map dict 
LANG_MAP = {
    "latin": "la",
    "la": "la",
    "greek": "greek",   # we'll verify the Greek code below
    "grc": "greek",
}



@dataclass
class Work:
    """
    A single work in the catalog.

    object_id   — Tesserae's internal identifier string, used in API calls
    author      — e.g. 'Vergil'
    title       — e.g. 'Aeneid'
    language    — 'latin' or 'greek'
    """
    object_id: str
    author: str
    title: str
    language: str
    cts_urn: str = ""

    def display(self) -> str:
        """Human-readable one-liner for the interactive menu."""
        return f"{self.author}, {self.title} ({self.language})"


def fetch_catalog(language: str | None = None) -> list[Work]:
    """
    Retrieve the full Tesserae text catalog, optionally filtered by language.

    The Tesserae API returns a JSON list of text objects. Each object looks
    roughly like:
        {
          "object_id": "urn:cts:latinLit:phi0690.phi003.perseus-lat2",
          "author": "Vergil",
          "title": "Aeneid",
          "language": "latin",
          ...
        }

    We normalise the language field so callers can use 'la', 'grc', etc.
    """
    params = {}
    if language:
        lang_code = LANG_MAP.get(language.lower(), language.lower())
        params["language"] = lang_code

    try:
        resp = requests.get(TESSERAE_API, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach Tesserae API. Detail: {exc}") from exc

    # API returns a bare JSON array, not a wrapped object
    items = resp.json()

    works = []
    for item in items:
        works.append(Work(
            object_id=item.get("id", ""),        # key is "id", not "object_id"
            author=item.get("author", "Unknown"),
            title=item.get("title", "Unknown"),
            language=item.get("language", ""),
            cts_urn=item.get("id", ""),
        ))

    works.sort(key=lambda w: (w.author.lower(), w.title.lower()))
    return works


    # Tesserae wraps results differently depending on version; handle both.
    # Some versions return a list directly; others wrap in {"texts": [...]}.
    if isinstance(raw, dict):
        items = raw.get("texts", raw.get("results", []))
    else:
        items = raw

    works = []
    for item in items:
        lang = LANG_MAP.get(item.get("language", "").lower(), item.get("language", ""))
        works.append(Work(
            object_id=item.get("object_id", ""),
            author=item.get("author", "Unknown"),
            title=item.get("title", "Unknown"),
            language=lang,
            cts_urn=item.get("object_id", ""),  # Tesserae uses CTS URNs as IDs
        ))

    if language:
        lang_norm = LANG_MAP.get(language.lower(), language.lower())
        works = [w for w in works if w.language == lang_norm]

    # Sort alphabetically by author then title for a consistent menu.
    works.sort(key=lambda w: (w.author.lower(), w.title.lower()))
    return works


def fetch_text(work: Work) -> list[str]:
    """
    Download and return the lines of a work as a list of strings.

    Tesserae exposes individual text tokens via:
        GET /texts/{object_id}/tokens/
    but for our purposes the raw text endpoint is more useful:
        GET /texts/{object_id}/

    The API returns a JSON object with a 'tokens' list or a 'units' list
    (depending on API version). We reconstruct prose paragraphs / verse
    lines from it.

    Returns a list of non-empty line strings, ready for chunking.
    """
    # URL-encode the object_id safely
    from urllib.parse import quote
    encoded_id = quote(work.object_id, safe="")
    url = f"{TESSERAE_API}{encoded_id}/"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not fetch text '{work.display()}' from Tesserae.\n"
            f"Detail: {exc}"
        ) from exc

    data = resp.json()

    # Tesserae returns tokens keyed by locus (book.line or book.chapter.section).
    # We reconstruct lines by joining tokens that share a locus prefix.
    tokens = data.get("tokens", [])
    if not tokens:
        # Try alternate key name
        tokens = data.get("units", [])

    if not tokens:
        raise RuntimeError(
            f"Tesserae returned no tokens for '{work.display()}'.\n"
            f"The text may not be available in this API version."
        )

    # Group tokens by their locus (line/section) to reconstruct readable lines.
    lines_by_locus: dict[str, list[str]] = {}
    for tok in tokens:
        locus = tok.get("locus", tok.get("tag", ""))
        form = tok.get("form", tok.get("display", ""))
        if locus not in lines_by_locus:
            lines_by_locus[locus] = []
        lines_by_locus[locus].append(form)

    lines = []
    for locus in sorted(lines_by_locus.keys()):
        line = " ".join(lines_by_locus[locus]).strip()
        if line:
            lines.append(line)

    return lines


def chunk_lines(lines: list[str], chunk_size: int, mode: str) -> Iterator[str]:
    """
    Split a list of lines into page-sized chunks.

    mode='poetry'   — chunk by line count (each line is a verse)
    mode='prose'    — chunk by word count (join all, split on spaces)

    Why separate chunking from fetching?
    The original code mixed chunking logic into create_document(), making
    it impossible to test either in isolation. This function is pure: given
    lines and a size, it yields chunks. No side effects.
    """
    if mode == "poetry":
        for i in range(0, len(lines), chunk_size):
            yield "\n".join(lines[i:i + chunk_size])
    elif mode == "prose":
        # Join everything, then split by word
        all_words = " ".join(lines).split()
        for i in range(0, len(all_words), chunk_size):
            yield " ".join(all_words[i:i + chunk_size])
    else:
        raise ValueError(f"Unknown mode '{mode}'. Use 'poetry' or 'prose'.")
