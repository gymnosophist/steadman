"""
lexicon.py — Dictionary lookup for Latin and Ancient Greek.

Latin strategy (two-tier):
  1. Whitaker's Words (primary) — clean, short glosses, no citation noise.
     Installed as a local package from github.com/blagae/whitakers_words.
  2. Lewis-Short JSON (fallback) — for words Whitaker's doesn't cover.
     Downloaded letter-by-letter from IohannesArnold/lewis-short-json,
     cached locally in platformdirs cache dir.

Greek strategy:
  LSJ9 short-definitions JSON from ciscoriordan/lsj9, cached locally.

---------------------------------------------------------------------------
IMPORTANT: lookup() takes the ORIGINAL INFLECTED TOKEN, not a CLTK lemma.
---------------------------------------------------------------------------
Whitaker's Words is a full morphological parser, not a plain dictionary —
it expects an inflected form ('languentibus') and works out the headword
itself. CLTK's lemmatiser, by contrast, often returns a bare stem
('langu') that is not a valid dictionary key for either Whitaker's or
Lewis-Short, and the bare stem is also more likely to collide with an
unrelated headword (e.g. 'hibern' matches both 'hibernus' [wintry] and
'Hibernus' [Irishman]).

So the pipeline is now:
    nlp.py:    token (inflected) ---------> lemma (for counting/grouping)
    lexicon.py: token (inflected) --------> Entry (lemma + POS + gloss)

Both nlp.py's lemma and lexicon.py's Entry.lemma are derived from the same
token, but independently — nlp.py needs a stable *grouping key* for
frequency counts, while lexicon.py needs the *correct dictionary headword*
for display. They are allowed to disagree (CLTK might say 'langu', while
Whitaker's says 'langueo' is the headword) — the rendering layer uses
Entry.lemma for display.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from dataclasses import dataclass

import requests
from platformdirs import user_cache_dir

from .morphology import reconstruct_headword # edited to relative import 

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache setup
# ---------------------------------------------------------------------------

CACHE_DIR = Path(user_cache_dir("steadman")) / "lexica"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Remote sources (Lewis-Short + LSJ9)
# ---------------------------------------------------------------------------

LS_BASE = (
    "https://raw.githubusercontent.com/IohannesArnold/lewis-short-json/master/ls_{letter}.json"
)

LSJ_URL = "https://raw.githubusercontent.com/ciscoriordan/lsj9/main/lsj9_short_defs.json"

# ---------------------------------------------------------------------------
# Whitaker's frequency ranking
#
# Whitaker's Words frequently returns SEVERAL competing analyses for one
# inflected form (different headwords that share an inflected form, or
# different senses of the same headword). Each analysis carries a
# `parsed_props["Frequency"]` field straight from Whitaker's own data,
# ranking how common that particular word/sense actually is in the
# corpus the dictionary was built from.
#
# We use this to pick the most plausible analysis instead of an arbitrary
# one. Without this, 'hibernis' could resolve to 'Irishman' (Frequency:
# Very Rare) just as easily as 'winter quarters' (Frequency: Uncommon) or
# 'wintry' (Frequency: Common) — purely because of dict ordering.
#
# Lower number = more frequent = preferred.
# ---------------------------------------------------------------------------

_FREQUENCY_RANK = {
    "Very Frequent": 0,
    "Frequent": 1,
    "Common": 2,
    "Uncommon": 3,
    "Rare": 4,
    "Very Rare": 5,
    "Inscription": 6,
    "Graffiti": 7,
    "Plinius": 8,
}
_UNKNOWN_FREQUENCY_RANK = 9  # sort dead last if Whitaker's gives us nothing

# Whitaker's stores a handful of the most basic suppletive irregulars
# (above all the copula 'sum'/'esse') as special-cased lexemes with
# roots=[] and parsed_props=None — i.e. NO frequency metadata at all.
# Left to _frequency_rank() alone, these would sort dead last (rank 9)
# and lose to almost anything, which is exactly backwards: 'sum' is the
# single most common verb in the language.
#
# We detect these the same way morphology.py does — by roots=[] AND an
# exact match on the full senses tuple (not just the first sense string,
# which is too short/generic to be a safe key on its own; e.g. 'sum' the
# copula and 'sumo' [take up] would both risk matching on a bare 'be').
_FORCE_RANK_FIRST_SENSES = {
    ("to be, exist", "also used to form verb perfect passive tenses with NOM PERF PPL"),
    ("be", "willing;", "wish;"),
}


def _frequency_rank(
    parsed_props: dict | None,
    senses: list[str] | None = None,
) -> int:
    if not parsed_props and senses:
        key = tuple(s.strip() for s in senses)
        if key in _FORCE_RANK_FIRST_SENSES:
            return -1  # beats every real rank, including 0 ("Very Frequent")
    if not parsed_props:
        return _UNKNOWN_FREQUENCY_RANK
    label = parsed_props.get("Frequency")
    return _FREQUENCY_RANK.get(label, _UNKNOWN_FREQUENCY_RANK)


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
    """
    Primary Latin lookup via Whitaker's Words.

    `word` should be the ORIGINAL INFLECTED TOKEN as it appeared in the
    text (e.g. 'languentibus', 'hibernis', 'gladios') — NOT a CLTK lemma
    stem. Whitaker's is a morphological parser: it expects inflected
    forms and resolves the headword internally. Passing it a bare stem
    like 'langu' will simply fail to match anything.

    Whitaker's commonly returns MULTIPLE candidate analyses for one
    inflected form — different headwords that happen to share a surface
    form, or different senses of the same headword (see module
    docstring for the 'hibernis' example). We collect every analysis
    that has at least one sense, then pick the single most frequent one
    using Whitaker's own Frequency metadata, rather than whichever
    analysis happens to come first in dict iteration order.
    """
    try:
        parser = _get_parser()
        if parser is None:
            return None

        result = parser.parse(word.lower().strip())

        candidates: list[tuple[int, Entry]] = []
        for form in result.forms:
            for analysis in form.analyses.values():
                lexeme = analysis.lexeme
                senses = lexeme.senses
                if not senses:
                    continue  # no gloss to show; skip this analysis entirely

                pos = lexeme.wordType.value if lexeme.wordType else ""
                roots = lexeme.roots

                # Prefer a fully reconstructed dictionary headword
                # ('gladius, -i, m.', 'cado, cadere, cecidi, casus')
                # over the bare Whitaker's stem. Falls back to the
                # stem itself when reconstruction isn't confident
                # (see morphology.py for exactly what is/isn't covered).
                lemma = reconstruct_headword(lexeme)
                if lemma is None:
                    lemma = roots[0] if roots else word

                rank = _frequency_rank(getattr(lexeme, "parsed_props", None), senses)
                candidates.append((
                    rank,
                    Entry(lemma=lemma, part_of_speech=pos, short_def=senses[0]),
                ))

        if not candidates:
            return None

        # Lowest rank number = most frequent = best candidate.
        candidates.sort(key=lambda pair: pair[0])
        return candidates[0][1]

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
    """
    Fallback Latin lookup via Lewis-Short JSON.

    `word` here should be a proper dictionary headword — ideally the
    headword Whitaker's would have used if it had a result (e.g.
    'langueo', not 'langu'). Lewis-Short is a plain dictionary keyed on
    real headwords; it does no morphological analysis, so handing it a
    bare CLTK stem will rarely match.
    """
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


def _lookup_latin(token: str, cltk_lemma: str | None = None) -> Entry | None:
    """
    Two-tier Latin lookup:
      1. Whitaker's Words, queried with the ORIGINAL INFLECTED TOKEN —
         clean, pedagogically appropriate glosses, frequency-ranked.
      2. Lewis-Short, queried with whatever headword we have at this
         point — fallback for words Whitaker's doesn't cover at all.

    Args:
        token:      The original inflected word form from the text.
        cltk_lemma: CLTK's lemma for this token, if available. Used only
                    as a last-resort Lewis-Short key if Whitaker's fails
                    AND a direct Lewis-Short lookup on the raw token also
                    fails. CLTK lemmas are sometimes bare stems
                    ('langu') rather than full headwords ('langueo'), so
                    this is intentionally the lowest-priority strategy.
    """
    entry = _lookup_latin_whitaker(token)
    if entry is not None:
        return entry

    # Whitaker's found nothing for the inflected form. Try Lewis-Short
    # directly on the raw token first (it occasionally matches an
    # uninflected headword as-is, e.g. an indeclinable word).
    entry = _lookup_latin_ls(token)
    if entry is not None:
        return entry

    # Last resort: try the CLTK lemma against Lewis-Short. This will
    # often fail (CLTK lemmas are frequently bare stems, not headwords),
    # but it's better than returning nothing.
    if cltk_lemma and cltk_lemma != token:
        return _lookup_latin_ls(cltk_lemma)

    return None


# ---------------------------------------------------------------------------
# LSJ9 (Greek)
# ---------------------------------------------------------------------------

_ml_index: dict[str, str] | None = None
_ml_stripped_index: dict[str, list[str]] | None = None

# ---------------------------------------------------------------------------
# lsj9 known-bad extractions
#
# lsj9's short_defs extraction sometimes grabs a stranded dialect/grammar
# note instead of skipping past it to the actual gloss -- e.g.
# lsj["πολύς"] == "Att. gen. dat" rather than "much, many". This shows up
# disproportionately on irregular, high-frequency words, where the LSJ
# entry head is a paragraph of principal-parts/dialect notes before the
# first sense. Reported upstream (ciscoriordan/lsj9); until that's fixed:
#
#   1. _GREEK_OVERRIDES hand-corrects the handful of extremely common
#      words that will appear on nearly every page, so they don't
#      silently mislead a reader.
#   2. _looks_like_stranded_note() is a defensive floor for everything
#      else: it can't guess the correct gloss, so it only ever turns a
#      confidently-wrong entry into a missing one, never the reverse.
#      This is NOT comprehensive -- some corrupted entries (e.g. ταχύς,
#      μέλας) don't match this pattern and will still slip through.
# ---------------------------------------------------------------------------

_GREEK_OVERRIDES: dict[str, str] = {
    "πολύς": "much, many",
    "μέγας": "great, large",
    "πᾶς": "all, every, whole",
    "εἷς": "one",
    "ἀγαθός": "good",
    "ἄγω": "lead, carry, bring, drive",
}

_STRANDED_NOTE_RE = re.compile(
    r"^(Att|Ion|Dor|Ep|Aeol|Boeot|Lacon|contr|irreg|collat)\.",
)


def _looks_like_stranded_note(gloss: str) -> bool:
    """True if `gloss` looks like a leftover dialect/grammar fragment
    rather than an actual English definition (see module notes above)."""
    text = gloss.strip()
    if not text:
        return True
    if _STRANDED_NOTE_RE.match(text):
        return True
    return False


def _strip_accents(word: str) -> str:
    """Reduce a polytonic Greek word to its bare letters, dropping accents,
    breathings, and iota subscripts. Used as a fallback match when a CLTK
    lemma's accentuation doesn't exactly match an LSJ9 headword's (e.g.
    recessive-accent citation forms, enclitic contexts, edition
    differences)."""
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _load_ml() -> tuple[dict[str, str], dict[str, list[str]]]:
    """Load LSJ9 short-definitions, using disk cache. Returns
    (exact_index, stripped_index) where exact_index maps accented
    headword -> gloss, and stripped_index maps accent-stripped headword
    -> list of accented headwords (for fallback matching)."""
    global _ml_index, _ml_stripped_index
    if _ml_index is not None and _ml_stripped_index is not None:
        return _ml_index, _ml_stripped_index

    disk_path = CACHE_DIR / "lsj9_short_defs.json"

    if disk_path.exists():
        raw = json.loads(disk_path.read_text(encoding="utf-8"))
    else:
        log.debug("Downloading LSJ9 from GitHub...")
        try:
            resp = requests.get(LSJ_URL, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            disk_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        except requests.RequestException as exc:
            log.warning("Could not download LSJ9: %s", exc)
            _ml_index, _ml_stripped_index = {}, {}
            return _ml_index, _ml_stripped_index

    stripped_index: dict[str, list[str]] = {}
    for headword in raw:
        stripped_index.setdefault(_strip_accents(headword), []).append(headword)

    _ml_index, _ml_stripped_index = raw, stripped_index
    return _ml_index, _ml_stripped_index


def _lookup_greek(token: str, cltk_lemma: str | None = None) -> Entry | None:
    """
    Look up an Ancient Greek word in LSJ9.

    Unlike Whitaker's, LSJ9 headwords are already dictionary citation
    forms rather than something a parser reconstructs — so cltk_lemma is
    tried FIRST here (it's usually closer to a real headword than the
    raw inflected token), with the raw token as a second exact-match
    attempt, then both are retried with accents stripped before giving
    up.
    """
    lsj, stripped_index = _load_ml()
    if not lsj:
        return None

    candidates = [c.strip() for c in (cltk_lemma, token) if c]

    for candidate in candidates:
        override = _GREEK_OVERRIDES.get(candidate)
        if override:
            return Entry(lemma=candidate, short_def=override)

    for candidate in candidates:
        gloss = lsj.get(candidate)
        if gloss and not _looks_like_stranded_note(gloss):
            return Entry(lemma=candidate, short_def=gloss[:120])

    for candidate in candidates:
        matches = stripped_index.get(_strip_accents(candidate))
        if matches:
            headword = matches[0]
            gloss = lsj[headword]
            if not _looks_like_stranded_note(gloss):
                return Entry(lemma=headword, short_def=gloss[:120])

    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def lookup(token: str, language: str, cltk_lemma: str | None = None) -> Entry | None:
    """
    Look up a single word and return an Entry, or None if not found.

    Args:
        token:      The ORIGINAL INFLECTED TOKEN as it appears in the
                    text (e.g. 'languentibus', not 'langu'). For Latin,
                    Whitaker's Words needs this to do its own
                    morphological analysis correctly.
        language:   'latin' or 'greek' (or Tesserae codes 'la'/'grc')
        cltk_lemma: Optional CLTK lemma for this token. For Latin, used
                    only as a last-resort Lewis-Short key (see
                    _lookup_latin). For Greek, tried FIRST against LSJ9,
                    since LSJ9 headwords are citation forms and the CLTK
                    lemma is usually closer to one than the raw token is.
    """
    lang = {"la": "latin", "grc": "greek"}.get(language, language)
    if lang == "latin":
        return _lookup_latin(token, cltk_lemma=cltk_lemma)
    elif lang == "greek":
        return _lookup_greek(token, cltk_lemma=cltk_lemma)
    else:
        raise ValueError(f"Unknown language '{language}'. Use 'latin' or 'greek'.")


def lookup_batch(
    tokens: list[str],
    language: str,
    cltk_lemmas: dict[str, str] | None = None,
    progress_callback=None,
) -> dict[str, Entry]:
    """
    Look up a list of original inflected tokens. Returns dict of
    token → Entry. Words with no result are silently skipped.

    Args:
        tokens:      Original inflected tokens from the text (NOT CLTK
                     lemma stems — see module docstring).
        language:    'latin' or 'greek'
        cltk_lemmas: Optional dict mapping token → CLTK lemma, used as a
                     last-resort Lewis-Short fallback key for Latin.
        progress_callback: Called with (current, total).
    """
    results = {}
    total = len(tokens)
    cltk_lemmas = cltk_lemmas or {}
    for i, token in enumerate(tokens):
        if progress_callback:
            progress_callback(i + 1, total)
        entry = lookup(token, language, cltk_lemma=cltk_lemmas.get(token))
        if entry:
            results[token] = entry
    return results