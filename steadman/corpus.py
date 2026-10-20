"""
corpus.py — Text retrieval and catalog management.

This module separates all corpus concerns from NLP and rendering.
Two sources are supported:

  1. Tesserae (Latin + Greek) — accessed via the public REST API.
     Endpoint: https://tesserae.caset.buffalo.edu/api/texts/
     This replaces the old CSV catalogs and the cltkreaders dependency.

  2. Text content — fetched from the Tesserae GitHub mirror.
     Endpoint: https://raw.githubusercontent.com/tesserae/tesserae/master/texts/

Why Tesserae over the Latin Library?
  The Latin Library is a great resource but its texts are HTML pages
  requiring scraping (fragile). Tesserae ships clean, tokenised plain
  text with Locus-based line keys — exactly what we need.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterator

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tesserae REST API
# ---------------------------------------------------------------------------

TESSERAE_API = "https://tesserae.caset.buffalo.edu/api/texts"

GITHUB_RAW = "https://raw.githubusercontent.com/tesserae/tesserae/master/texts"

# ---------------------------------------------------------------------------
# Language mapping
#
# The Tesserae API uses its own language strings in the `language` field of
# each returned object. Normalize either full names or short codes
# to "latin" and "greek" internally.
#
# We accept several user-facing spellings and normalise them to the Tesserae
# strings so both the query param and the client-side filter use the same
# value.
# ---------------------------------------------------------------------------

# Language slugs as Tesserae understands them for the ?language= query param.
# The API uses short codes ('la', 'grc'), NOT the full names ('latin', 'greek').
# We normalise user input to full names internally (for catalog filtering),
# but must convert back to short codes when querying the API.
LANG_MAP: dict[str, str] = {
    "latin": "latin",
    "la": "latin",
    "greek": "greek",
    "grc": "greek",
}

# Short codes for the Tesserae API query param
LANG_API_CODE: dict[str, str] = {
    "latin": "la",
    "greek": "grc",
}

# Maps Tesserae language strings to the directory names used in the GitHub
# text mirror.  Latin lives in texts/la/, Greek in texts/grc/.
GITHUB_LANG_DIR: dict[str, str] = {
    "latin": "la",
    "greek": "grc",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Work:
    object_id: str
    author: str
    title: str
    language: str  # normalised to Tesserae strings: "latin" | "greek"
    cts_urn: str = ""
    part_num: str = ""  # e.g. "14" for Book 14; "" for whole works

    def display(self) -> str:
        """Human-readable one-liner for the interactive menu."""
        return f"{self.author}, {self.title} ({self.language})"


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


def _github_filename(work: Work) -> str:
    """
    Convert a Tesserae object_id to its GitHub repo filename.

    Tesserae v6 splits long works into parts:
        'ammianus.rerum_gestarum.part.14.tess'
    GitHub stores the whole work:
        'ammianus.rerum_gestarum.tess'

    We strip '.part.N' and '.book.N' suffixes to get the base filename.
    """
    name = work.object_id
    name = re.sub(
        r"\.part\.\d+", "", name
    )  # 'ammianus.rerum_gestarum.part.14.tess' → 'ammianus.rerum_gestarum.tess'
    name = re.sub(r"\.book\.\d+", "", name)  # handle .book.N variants too
    return name


# ---------------------------------------------------------------------------
# Catalog retrieval
# ---------------------------------------------------------------------------


def fetch_catalog(language: str | None = None) -> list[Work]:
    """
    Retrieve the full Tesserae text catalog, optionally filtered by language.

    The Tesserae API returns a bare JSON array of objects. Each object looks
    roughly like:

        {
          "id":       "homer.iliad.tess",
          "author":   "Homer",
          "title":    "Iliad",
          "language": "greek",
          ...
        }

    We do filtering in two layers:
      1. Server-side: pass ?language=<code> as a query param so the API
         returns only matching texts. This is fast and reduces payload size.
      2. Client-side: filter again on the returned objects. This guards
         against the API ignoring the param or returning mixed results.

    Both layers use the same normalised language string from LANG_MAP.
    """
    # --- normalise the caller's language string ("grc" → "greek", etc.) ---
    lang_norm: str | None = None
    params: dict[str, str] = {}

    if language:
        lang_norm = LANG_MAP.get(language.lower())
        if lang_norm is None:
            # Unknown language string — pass it through and hope for the best,
            # but warn the user so they know the mapping is missing.
            log.warning(
                "Unknown language %r — not in LANG_MAP. "
                "Passing raw value to API; results may be empty.",
                language,
            )
            lang_norm = language.lower()
        params["language"] = LANG_API_CODE.get(lang_norm, lang_norm)

    # --- hit the API ---
    try:
        resp = requests.get(TESSERAE_API, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach Tesserae API. Detail: {exc}") from exc

    # The API returns a bare JSON array — NOT a dict like {"texts": [...]}.
    items: list[dict] = resp.json()

    if not isinstance(items, list):
        # Defensive: if the API shape ever changes, fail loudly.
        raise RuntimeError(
            f"Tesserae API returned unexpected type {type(items).__name__}. "
            f"Expected a list. First 200 chars: {str(items)[:200]}"
        )

    # Log a sample item when --verbose is enabled.
    if items:
        log.debug("Tesserae sample item: %s", items[0])

    # --- build Work objects ---
    works: list[Work] = []
    for item in items:
        # The language field in the returned object should already match
        # lang_norm (since we filtered server-side), but we store it as-is
        # so we can debug mismatches.
        works.append(
            Work(
                object_id=item.get("id", ""),  # Tesserae v6 uses "id", not "object_id"
                author=item.get("author", "Unknown"),
                title=item.get("title", "Unknown"),
                language=LANG_MAP.get(item.get("language", "").lower(), item.get("language", "")),
                cts_urn=item.get("id", ""),
                part_num=str(item.get("part_num") or ""),
            )
        )

    # --- client-side filter (second layer of defence) ---
    # The REST API stores full language names ('latin', 'greek'); the
    # GitHub fallback stores short codes ('la', 'grc'). We accept both
    # so the filter works regardless of which source populated the catalog.
    if lang_norm:
        accepted = {lang_norm}  # e.g. {'latin'}
        accepted.update(  # add short codes
            k for k, v in LANG_MAP.items() if v == lang_norm
        )  # e.g. {'latin','la'}
        before = len(works)
        works = [w for w in works if w.language in accepted]
        after = len(works)
        if before != after:
            log.debug(
                "Client-side language filter: dropped %d non-%s works.",
                before - after,
                lang_norm,
            )

    # Sort alphabetically by author then title for a consistent menu.
    works.sort(key=lambda w: (w.author.lower(), w.title.lower()))
    return works


# ---------------------------------------------------------------------------
# Text retrieval
# ---------------------------------------------------------------------------


def fetch_text(work: Work) -> list[str]:
    """
    Fetch the plain-text lines of a work from the Tesserae GitHub mirror.

    Each line in a .tess file looks like:
        <vergil. aen. 1.1>    arma virumque cano, Troiae qui primus ab oris

    We split on '>' to separate the locus tag from the text, then optionally
    filter to a specific book/part when work.part_num is set.
    """
    language = LANG_MAP.get(work.language.lower(), work.language.lower())
    lang_dir = GITHUB_LANG_DIR.get(language, language)
    filename = _github_filename(work)
    url = f"{GITHUB_RAW}/{lang_dir}/{filename}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not fetch '{work.display()}' from GitHub.\nURL tried: {url}\nDetail: {exc}"
        ) from exc

    part_num = work.part_num or None  # treat empty string as "no filter"

    lines: list[str] = []
    for raw_line in resp.text.splitlines():
        raw_line = raw_line.strip()

        # Skip blanks and comment lines (# marks metadata in .tess format).
        if not raw_line or raw_line.startswith("#"):
            continue

        # Every content line must contain a '>' separating locus from text.
        if ">" not in raw_line:
            continue

        locus, text = raw_line.split(">", 1)
        text = text.strip()

        # Sanity-check: a valid locus starts with '<' and the text after
        # the split should be non-empty prose, not another tag fragment.
        # Lines like '<ambrose. ep. 40.11.Sed disciplinae...' have no
        # closing '>' before the text — they split at a '>' inside the
        # sentence instead, producing a locus that doesn't start with '<'
        # or text that is suspiciously short. Skip them rather than
        # emitting garbled content.
        if not locus.startswith("<"):
            continue
        if not text:
            continue

        # If this Work is a named part (e.g. Book 14), skip lines from other
        # books. Locus format: '<amm. 14.1.1' — the first integer after the
        # abbreviation is the book/part number.
        if part_num:
            nums = re.findall(r"\d+", locus)
            if not nums or nums[0] != str(part_num):
                continue

        lines.append(text)

    return lines


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_lines(lines: list[str], chunk_size: int, mode: str) -> Iterator[str]:
    """
    Split a list of lines into page-sized chunks.

    mode='poetry'  — chunk by line count (each line is a verse)
    mode='prose'   — chunk by word count (join all, then split on spaces)

    Chunking is kept separate from fetching so each function can be tested
    independently. This function is pure: given lines and a size, it yields
    chunks with no side effects.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    if mode == "poetry":
        for i in range(0, len(lines), chunk_size):
            yield "\n".join(lines[i : i + chunk_size])
    elif mode == "prose":
        all_words = " ".join(lines).split()
        for i in range(0, len(all_words), chunk_size):
            yield " ".join(all_words[i : i + chunk_size])
    else:
        raise ValueError(f"Unknown mode {mode!r}. Use 'poetry' or 'prose'.")
