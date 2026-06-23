"""
corpus.py — Text retrieval and catalog management.

Two sources:
  1. Tesserae REST API — catalog of available texts (Latin + Greek)
     Endpoint: https://tesserae.caset.buffalo.edu/api/texts
  2. tesserae/tesserae GitHub repo — raw .tess files for text content
     The Tesserae v6 API serves only HTML for individual text endpoints;
     the raw text lives in the GitHub repo as .tess files.

.tess format:
  Each line: <author.work book.line> text content
  e.g. <verg. aen. 1.1> Arma virumque cano, Troiae qui primus ab oris
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Iterator

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

TESSERAE_API = "https://tesserae.caset.buffalo.edu/api/texts"
GITHUB_RAW = "https://raw.githubusercontent.com/tesserae/tesserae/master/texts"

# Tesserae v6 language codes
LANG_MAP = {
    "latin": "la",
    "la": "la",
    "greek": "greek",
    "grc": "greek",
}

# Maps Tesserae language codes to GitHub directory names
GITHUB_LANG_DIR = {
    "la": "la",
    "greek": "grc",
}


# ---------------------------------------------------------------------------
# Work dataclass
# ---------------------------------------------------------------------------

@dataclass
class Work:
    """A single work in the Tesserae catalog."""
    object_id: str       # Tesserae ID, e.g. 'ammianus.rerum_gestarum.part.14.tess'
    author: str          # e.g. 'Ammianus Marcellinus'
    title: str           # e.g. 'Res Gestae, Book 14'
    language: str        # Tesserae code: 'la' or 'greek'
    cts_urn: str = ""
    part_num: str = ""   # e.g. '14' for Book 14, '' for whole works

    def display(self) -> str:
        """Human-readable one-liner for the interactive menu."""
        return f"{self.author}, {self.title} ({self.language})"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def fetch_catalog(language: str | None = None) -> list[Work]:
    """
    Retrieve the Tesserae catalog, optionally filtered by language.

    The API returns a bare JSON array (not a wrapped object).
    Each item has fields: id, author, title, language, part_num, etc.
    Language is passed as a query parameter using Tesserae's own codes
    ('la' for Latin, 'greek' for Greek).
    """
    params = {}
    if language:
        lang_code = LANG_MAP.get(language.lower(), language.lower())
        params["language"] = lang_code

    try:
        resp = requests.get(TESSERAE_API, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not reach Tesserae API at {TESSERAE_API}.\n"
            f"Check your network connection. Detail: {exc}"
        ) from exc

    items = resp.json()  # bare list

    works = []
    for item in items:
        works.append(Work(
            object_id=item.get("id", ""),
            author=item.get("author", "Unknown"),
            title=item.get("title", "Unknown"),
            language=item.get("language", ""),
            cts_urn=item.get("id", ""),
            part_num=str(item.get("part_num", "")),
        ))

    works.sort(key=lambda w: (w.author.lower(), w.title.lower()))
    return works


# ---------------------------------------------------------------------------
# Text fetching
# ---------------------------------------------------------------------------

def _github_filename(work: Work) -> str:
    """
    Convert a Tesserae v6 object_id to its GitHub repo filename.

    Tesserae v6 splits works into parts:
        'ammianus.rerum_gestarum.part.14.tess'
    The GitHub repo stores the whole work:
        'ammianus.rerum_gestarum.tess'

    We strip '.part.N' and '.book.N' suffixes.
    """
    name = work.object_id
    name = re.sub(r'\.part\.\d+', '', name)
    name = re.sub(r'\.book\.\d+', '', name)
    return name


def fetch_text(work: Work) -> list[str]:
    """
    Fetch text lines from the tesserae/tesserae GitHub repo.

    Downloads the whole .tess file and filters to the correct
    book/part when work.part_num is set.

    .tess line format: <abbreviation. book.line.section> text
    e.g. <amm. 14.1.1> Post emensos insuperabilis expeditionis...

    For partial works (e.g. Book 14 of Ammianus), we filter by
    matching the first number in the locus tag against part_num.
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

    part_num = work.part_num or ""

    lines = []
    for raw_line in resp.text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line or raw_line.startswith("#"):
            continue
        if ">" not in raw_line:
            continue

        locus, text = raw_line.split(">", 1)
        text = text.strip()
        if not text:
            continue

        # Filter to correct book/part if this is a partial work
        if part_num:
            nums = re.findall(r'\d+', locus)
            if not nums or nums[0] != str(part_num):
                continue

        lines.append(text)

    return lines


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_lines(lines: list[str], chunk_size: int, mode: str) -> Iterator[str]:
    """
    Split lines into page-sized chunks.

    mode='poetry' — chunk by line count (one line = one verse)
    mode='prose'  — chunk by word count (join all words, split evenly)
    """
    if mode == "poetry":
        for i in range(0, len(lines), chunk_size):
            yield "\n".join(lines[i:i + chunk_size])
    elif mode == "prose":
        all_words = " ".join(lines).split()
        for i in range(0, len(all_words), chunk_size):
            yield " ".join(all_words[i:i + chunk_size])
    else:
        raise ValueError(f"Unknown mode '{mode}'. Use 'poetry' or 'prose'.")