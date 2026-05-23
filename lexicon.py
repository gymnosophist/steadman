"""
lexicon.py — Dictionary lookup for Latin and Ancient Greek.

Latin strategy (two-tier):
  1. Whitaker's Words (primary) — clean, short glosses, no citation noise.
     Installed as a local package from github.com/blagae/whitakers_words.
  2. Lewis-Short JSON (fallback) — for words Whitaker's doesn't cover.
     Downloaded letter-by-letter from IohannesArnold/lewis-short-json,
     cached locally in platformdirs cache dir.

Greek strategy:
  Middle Liddell JSON from PerseusDL/lexica, cached locally.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from dataclasses import dataclass

import requests
from platformdirs import user_cache_dir

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache setup
# ---------------------------------------------------------------------------

CACHE_DIR = Path(user_cache_dir("steadman")) / "lexica"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Remote sources (Lewis-Short + Middle Liddell)
# ---------------------------------------------------------------------------

LS_BASE = (
    "https://raw.githubusercontent.com/IohannesArnold/lewis-short-json/master/ls_{letter}.json"
)

ML_URL = (
    "https://raw.githubusercontent.com/PerseusDL/lexica/master/CTS_XML_TEI/perseus/"
    "pdllex/grc/ls/grc.ls.perseus-eng1.json"
)

# ---------------------------------------------------------------------------
# Entry dataclass
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    """
    A single dictionary entry.

    lemma          — headword (e.g. 'miles', 'ἄνθρωπος')
    part_of_speech — brief label (e.g. 'Noun', 'Verb')
    short_def      — one-line gloss for the facing vocabulary column
    """
    lemma: str
    part_of_speech: str = ""
    short_def: str = ""

    def format_vocab_entry(self) -> tuple[str, str]:
        """Return (bold_part, plain_part) for PDF rendering."""
        bold = self.lemma
        if self.part_of_speech:
            bold += f" ({self.part_of_speech})"
        bold += ": "
        # Clean up slash-separated alternatives: 'war/warfare' → 'war, warfare'
        plain = self.short_def.replace("/", ", ")
        return bold, plain


# ---------------------------------------------------------------------------
# Whitaker's Words (Latin primary)
# ---------------------------------------------------------------------------

_whitaker_parser = None


def _get_parser():
    global _whitaker_parser
    if _whitaker_parser is None:
        try:
            from whitakers_words.parser import Parser
            _whitaker_parser = Parser()
        except ImportError:
            log.warning(
                "whitakers_words not installed. "
                "Latin lookups will fall back to Lewis-Short only.\n"
                "Install with: pip install git+https://github.com/blagae/whitakers_words.git"
            )
    return _whitaker_parser


def _lookup_latin_whitaker(word: str) -> Entry | None:
    """Primary Latin lookup via Whitaker's Words."""
    try:
        parser = _get_parser()
        if parser is None:
            return None
        result = parser.parse(word.lower().strip())
        for form in result.forms:
            for analysis in form.analyses.values():
                lexeme = analysis.lexeme
                senses = lexeme.senses
                if not senses:
                    continue
                pos = lexeme.wordType.value if lexeme.wordType else ""
                roots = lexeme.roots
                lemma = roots[0] if roots else word
                return Entry(
                    lemma=lemma,
                    part_of_speech=pos,
                    short_def=senses[0],
                )
    except Exception as exc:
        log.debug("Whitaker lookup failed for '%s': %s", word, exc)
    return None


# ---------------------------------------------------------------------------
# Lewis-Short (Latin fallback)
# ---------------------------------------------------------------------------

_ls_cache: dict[str, list[dict]] = {}


def _load_ls_letter(letter: str) -> list[dict]:
    """
    Load Lewis-Short entries for a given first letter, using disk cache.
    Downloads from GitHub on first use, then reads from local cache.
    """
    letter = letter.upper()
    if letter in _ls_cache:
        return _ls_cache[letter]

    disk_path = CACHE_DIR / f"ls_{letter}.json"

    if disk_path.exists():
        data = json.loads(disk_path.read_text(encoding="utf-8"))
    else:
        url = LS_BASE.format(letter=letter)
        log.debug("Downloading Lewis-Short %s from %s", letter, url)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            disk_path.write_text(json.dumps(data), encoding="utf-8")
        except requests.RequestException as exc:
            log.warning("Could not download LS_%s: %s", letter, exc)
            data = []

    _ls_cache[letter] = data
    return data


def _flatten(senses, out: list) -> None:
    """Recursively flatten nested senses list into a list of strings."""
    for item in senses:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, list):
            _flatten(item, out)


def _extract_short_def(senses) -> str:
    """
    Extract a one-line gloss from a Lewis-Short senses list.

    Lewis-Short entries often begin with morphological preamble ending in '), ':
        'Gen. plur. virtutium ... ), f. vir, manliness, manhood...'
    We strip everything up to and including the last '), ' to get the gloss.
    """
    if not senses:
        return ""

    candidates: list[str] = []
    _flatten(senses, candidates)

    for text in candidates:
        text = text.strip()
        if not text:
            continue
        # Skip pure Roman numeral / section headers
        if re.fullmatch(r"[IVXivxA-Da-d]+\.?", text):
            continue
        # If the string contains '), ', the real def starts after it
        if ")," in text:
            after_paren = re.split(r"\),\s*", text)[-1].strip()
            if after_paren and not re.match(r"^[a-z]+\.\s", after_paren[:8]):
                text = after_paren
        # Skip if it still looks like citation noise
        if re.search(r"\.[a-z]{1,3}\.\.$", text):
            continue
        # Skip citation-heavy strings
        citation_count = len(re.findall(r"\b(?:Cic|Liv|Ov|Verg|Plaut|Sen)\.", text))
        if citation_count > 2 and len(text) > 200:
            continue
        return text[:120].strip()
    return ""


def _lookup_latin_ls(word: str) -> Entry | None:
    """Fallback Latin lookup via Lewis-Short JSON."""
    word_lower = word.lower().strip()
    if not word_lower:
        return None

    first_letter = word_lower[0].upper()
    letters_to_try = [first_letter]
    if first_letter == "J":
        letters_to_try.append("I")
    elif first_letter == "I":
        letters_to_try.append("J")

    for letter in letters_to_try:
        entries = _load_ls_letter(letter)
        for entry in entries:
            key = entry.get("key", "").lower()
            if key == word_lower or re.sub(r"\d+$", "", key) == word_lower:
                short_def = _extract_short_def(entry.get("senses", []))
                if not short_def:
                    continue
                return Entry(
                    lemma=entry.get("key", word),
                    part_of_speech=entry.get("part_of_speech", ""),
                    short_def=short_def,
                )
    return None


def _lookup_latin(word: str) -> Entry | None:
    """
    Two-tier Latin lookup:
      1. Whitaker's Words — clean, pedagogically appropriate glosses
      2. Lewis-Short — fallback for words Whitaker's doesn't cover
    """
    entry = _lookup_latin_whitaker(word)
    if entry is not None:
        return entry
    return _lookup_latin_ls(word)


# ---------------------------------------------------------------------------
# Middle Liddell (Greek)
# ---------------------------------------------------------------------------

_ml_index: dict[str, dict] | None = None


def _load_ml() -> dict[str, dict]:
    """Load Middle Liddell JSON, using disk cache."""
    global _ml_index
    if _ml_index is not None:
        return _ml_index

    disk_path = CACHE_DIR / "middle_liddell.json"

    if disk_path.exists():
        raw = json.loads(disk_path.read_text(encoding="utf-8"))
    else:
        log.debug("Downloading Middle Liddell from GitHub...")
        try:
            resp = requests.get(ML_URL, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            disk_path.write_text(json.dumps(raw), encoding="utf-8")
        except requests.RequestException as exc:
            log.warning("Could not download Middle Liddell: %s", exc)
            _ml_index = {}
            return _ml_index

    entries = raw if isinstance(raw, list) else raw.get("entries", [])
    index = {}
    for entry in entries:
        key = entry.get("key", entry.get("hdwd", "")).strip()
        if key:
            index[key] = entry
    _ml_index = index
    return _ml_index


def _lookup_greek(word: str) -> Entry | None:
    """Look up an Ancient Greek word in the Middle Liddell."""
    if not word:
        return None
    index = _load_ml()
    entry = index.get(word.strip())
    if not entry:
        return None
    short_def = _extract_short_def(entry.get("senses", []))
    if not short_def:
        short_def = entry.get("meaning", "")[:120]
    if not short_def:
        return None
    return Entry(
        lemma=entry.get("key", word),
        part_of_speech=entry.get("part_of_speech", ""),
        short_def=short_def,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def lookup(word: str, language: str) -> Entry | None:
    """
    Look up a single lemma and return an Entry, or None if not found.

    Args:
        word:     The lemma to look up (should already be lemmatised).
        language: 'latin' or 'greek' (or Tesserae codes 'la'/'grc')
    """
    lang = {"la": "latin", "grc": "greek"}.get(language, language)
    if lang == "latin":
        return _lookup_latin(word)
    elif lang == "greek":
        return _lookup_greek(word)
    else:
        raise ValueError(f"Unknown language '{language}'. Use 'latin' or 'greek'.")


def lookup_batch(
    words: list[str],
    language: str,
    progress_callback=None,
) -> dict[str, Entry]:
    """
    Look up a list of lemmas. Returns dict of lemma → Entry.
    Words with no result are silently skipped.
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