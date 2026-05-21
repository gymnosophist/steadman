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

TESSERAE_API = "https://tesserae.caset.buffalo.edu/api/texts" # removed trailing slash, added '/api/'
# added github links 
GITHUB_API = "https://api.github.com/repos/tesserae/tesserae/contents/texts"
GITHUB_RAW = "https://raw.githubusercontent.com/tesserae/tesserae/master/texts"

# Language slugs as Tesserae understands them.
# slight edits to lang_map dict 
LANG_MAP = {
    "latin": "la",
    "la": "la",
    "greek": "greek",   # we'll verify the Greek code below
    "grc": "greek",
}

GITHUB_LANG_DIR = {
    "la": "la",
    "greek": "grc",
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
    
def _github_filename(work: Work) -> str:
    """
    Convert a Tesserae v6 object_id to its GitHub repo filename.

    v6 splits works into parts: 'ammianus.rerum_gestarum.part.14.tess'
    GitHub stores the whole work:  'ammianus.rerum_gestarum.tess'

    We strip '.part.N' and keep the base name.
    """
    import re
    name = work.object_id  # e.g. 'ammianus.rerum_gestarum.part.14.tess'
    name = re.sub(r'\.part\.\d+', '', name)   # → 'ammianus.rerum_gestarum.tess'
    name = re.sub(r'\.book\.\d+', '', name)   # handle .book.N variants too
    return name


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
    Fetch text lines from the tesserae/tesserae GitHub repo.

    Uses the raw file URL directly. The .tess format is:
        <author.work book.line>TABtext content
    We strip the locus tag and return the text lines only.
    """
    lang_dir = GITHUB_LANG_DIR.get(work.language, work.language)
    filename = _github_filename(work)
    url = f"{GITHUB_RAW}/{lang_dir}/{filename}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not fetch '{work.display()}' from GitHub.\n"
            f"URL tried: {url}\nDetail: {exc}"
        ) from exc

    lines = []
    # Replace the tab-splitting block with this:
    for raw_line in resp.text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line or raw_line.startswith("#"):
            continue
        # Format: <locus> text  (space after closing >, no tab)
        if ">" in raw_line:
            _, text = raw_line.split(">", 1)
            text = text.strip()
            if text:
                lines.append(text)

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
