"""
lexicon.py — Dictionary lookup for Latin and Ancient Greek.

Old approach: load a 40MB XML file into memory at module import time.
  tree = ET.parse('lexica/Lewis_Short_XML/lat.ls.perseus-eng1.xml')
  entries = tree.xpath('//entryFree')

This has two problems:
  1. It requires the file to exist at a hardcoded relative path.
  2. It parses the entire XML tree on every startup, even if you're
     only looking up three words.

New approach: use the Logeion API (https://logeion.uchicago.edu), which
is a free, public-facing service maintained by the University of Chicago
that wraps Lewis-Short (Latin) and LSJ/Middle Liddell (Greek).

The API is simple:
  GET https://logeion.uchicago.edu/lexica/search/{word}

This returns JSON with definitions from multiple lexica. We extract
Lewis-Short entries for Latin and Middle Liddell entries for Greek.

For offline use or bulk processing, we cache responses on disk in the
platformdirs cache directory so we don't hammer the API on repeated runs.
"""

from __future__ import annotations

import json
import logging
import hashlib
import re
from pathlib import Path
from dataclasses import dataclass

import requests
from platformdirs import user_cache_dir

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache setup
# ---------------------------------------------------------------------------

CACHE_DIR = Path(user_cache_dir("steadman")) / "lexicon_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LOGEION_URL = "https://logeion.uchicago.edu/lexica/search/{word}"
REQUEST_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Data class for a dictionary entry
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    """
    A single lexicon entry.

    lemma          — dictionary headword (e.g. 'amor', 'λόγος')
    part_of_speech — brief label if available (e.g. 'n.', 'v.')
    short_def      — one-line gloss, suitable for facing vocab
    full_def       — longer definition if available
    """
    lemma: str
    part_of_speech: str = ""
    short_def: str = ""
    full_def: str = ""

    def format_vocab_entry(self) -> tuple[str, str]:
        """
        Return (bold_part, plain_part) for rendering in the vocabulary column.

        Example:
          bold:  'amor, amoris m.'
          plain: 'love, affection, desire'
        """
        bold = self.lemma
        if self.part_of_speech:
            bold += f" {self.part_of_speech}"
        bold += ": "
        return bold, self.short_def


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cache_path(word: str) -> Path:
    """Deterministic cache filename for a given word."""
    # Use a hash so non-ASCII Greek characters don't cause filesystem issues.
    key = hashlib.md5(word.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.json"


def _fetch_logeion(word: str) -> dict:
    """
    Fetch raw Logeion JSON for a word, using disk cache if available.

    The cache is permanent (no TTL) because dictionary definitions don't
    change. This means a large text can be re-run instantly on the second
    pass.
    """
    cache = _cache_path(word)
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache.unlink()  # corrupt cache entry; delete and re-fetch

    try:
        url = LOGEION_URL.format(word=requests.utils.quote(word))
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        log.debug("Logeion lookup failed for '%s': %s", word, exc)
        return {}

    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def _strip_html(text: str) -> str:
    """Remove HTML tags from definition strings."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_latin_entry(data: dict) -> Entry | None:
    """
    Extract a Lewis-Short entry from Logeion's JSON response.

    Logeion returns a list under the key 'Lewis-Short' (or similar).
    Each item typically has 'entry' (HTML-formatted) and 'key' fields.
    """
    # Key names vary slightly between Logeion API versions
    for key in ("Lewis-Short", "lewis-short", "LewisShort", "LS"):
        entries = data.get(key, [])
        if entries:
            break
    else:
        return None

    if not entries:
        return None

    raw = entries[0]  # Take the first (most relevant) entry
    full = _strip_html(raw.get("entry", ""))
    if not full:
        return None

    # The headword is usually the first token before a comma or whitespace
    headword = raw.get("key", full.split()[0] if full else "")

    # Extract a short definition: first sentence or clause, max 120 chars
    # Lewis-Short entries often start with "I. <sense>; II. <sense>"
    # We want just the first gloss.
    short = re.split(r"[;.]", full)[0][:120].strip()
    # Remove Roman numeral section headers like "I." "A." at the start
    short = re.sub(r"^[IVXivxa-z]+\.\s*", "", short).strip()

    return Entry(
        lemma=headword,
        short_def=short,
        full_def=full,
    )


def _parse_greek_entry(data: dict) -> Entry | None:
    """
    Extract a Middle Liddell entry from Logeion's JSON response.

    For Greek we prefer Middle Liddell over the full LSJ because its
    definitions are shorter and more suitable for a facing vocabulary —
    just as Pharr used an abridged lexicon in his Homeric reader.
    """
    for key in ("Middle Liddell", "middle-liddell", "MiddleLiddell", "ML"):
        entries = data.get(key, [])
        if entries:
            break
    else:
        # Fall back to LSJ if Middle Liddell unavailable
        for key in ("LSJ", "lsj", "Liddell-Scott"):
            entries = data.get(key, [])
            if entries:
                break
        else:
            return None

    if not entries:
        return None

    raw = entries[0]
    full = _strip_html(raw.get("entry", ""))
    if not full:
        return None

    headword = raw.get("key", full.split()[0] if full else "")
    short = re.split(r"[;.]", full)[0][:120].strip()
    short = re.sub(r"^[IVXivxa-z]+\.\s*", "", short).strip()

    return Entry(
        lemma=headword,
        short_def=short,
        full_def=full,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def lookup(word: str, language: str) -> Entry | None:
    """
    Look up a single word and return an Entry, or None if not found.

    Args:
        word:     The lemma to look up (should already be lemmatised).
        language: 'latin' or 'greek'

    This is the single public function callers should use.
    All caching, HTTP, and parsing is handled internally.
    """
    if not word or not word.strip():
        return None

    data = _fetch_logeion(word.strip())
    if not data:
        return None

    if language == "latin":
        return _parse_latin_entry(data)
    elif language == "greek":
        return _parse_greek_entry(data)
    else:
        raise ValueError(f"Unknown language '{language}'. Use 'latin' or 'greek'.")


def lookup_batch(
    words: list[str],
    language: str,
    progress_callback=None,
) -> dict[str, Entry]:
    """
    Look up a list of words and return a dict mapping lemma → Entry.

    Skips words that return no result (common words, proper nouns, etc.).
    progress_callback, if provided, is called with (current, total) on
    each lookup — useful for showing a progress bar in the CLI.
    """
    results = {}
    total = len(words)
    for i, word in enumerate(words):
        if progress_callback:
            progress_callback(i + 1, total)
        entry = lookup(word, language)
        if entry:
            results[word] = entry
    return results
