"""
nlp.py — NLP pipeline: tokenisation, lemmatisation, frequency filtering.

The old code mixed lemmatisation into corpus loading AND into page creation,
making it run twice and making both functions hard to test. Here it lives
in one place.

CLTK dependency strategy:
  CLTK (Classical Language Toolkit) is the right library here. However,
  its import cost is high and its models require a ~500MB download on
  first use. We import it lazily (inside functions) so the CLI remains
  snappy for users who just want to browse the catalog.

  If CLTK is not installed, we fall back to a simple whitespace tokeniser
  and skip lemmatisation — the program still runs, just with raw word forms
  rather than dictionary headwords.

Greek normalisation:
  Ancient Greek text from Tesserae uses Unicode polytonic encoding.
  We do NOT convert to betacode — that was necessary for the old
  Middle Liddell XML lookup (which keyed entries on betacode strings),
  but Logeion accepts Unicode directly.
"""

from __future__ import annotations

import re
import logging
from collections import Counter
from typing import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop word lists
# ---------------------------------------------------------------------------

# Latin stop words: extremely common words a reader can be assumed to know.
# Drawn from CLTK's list plus common abbreviations and Roman numerals.
LATIN_STOPS = {
    # pronouns & demonstratives
    "ego", "tu", "nos", "vos", "is", "ea", "id", "hic", "haec", "hoc",
    "ille", "illa", "illud", "ipse", "ipsa", "ipsum", "idem", "qui", "quae",
    "quod", "quis", "quid",
    # prepositions
    "in", "ad", "ab", "ex", "de", "cum", "per", "sub", "pro", "ante",
    "post", "inter", "super", "ob", "sine", "contra",
    # conjunctions & particles
    "et", "sed", "aut", "atque", "ac", "vel", "nec", "neque", "nam",
    "enim", "autem", "tamen", "ergo", "igitur", "itaque", "ita", "non",
    "nunc", "iam", "tum", "ubi", "ut", "ne", "si",
    # common verbs
    "sum", "esse", "est", "sunt", "fui", "esse", "possum",
    # Roman numerals / abbreviations that slip through tokenisation
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "a", "m", "p", "c", "l", "q", "t",
    # punctuation tokens
    "", "punc", ",", ".", ";", ":", "?", "!", "-",
}

# Greek stop words: equivalent set for Ancient Greek.
GREEK_STOPS = {
    # articles
    "ὁ", "ἡ", "τό", "οἱ", "αἱ", "τά",
    # pronouns
    "αὐτός", "αὐτή", "αὐτό", "ἐγώ", "σύ", "ἡμεῖς", "ὑμεῖς",
    "οὗτος", "αὕτη", "τοῦτο", "ἐκεῖνος",
    # conjunctions & particles
    "καί", "δέ", "μέν", "γάρ", "ἀλλά", "ὅτι", "εἰ", "ἐν", "εἰς",
    "ἐκ", "ἐξ", "ἐπί", "πρός", "παρά", "κατά", "περί", "ὑπό",
    "οὐ", "οὐκ", "οὐχ", "μή", "οὖν", "δή", "τε", "ἄρα", "ὡς",
    # common verbs
    "εἰμί", "εἶναι",
    # punctuation
    "", "·", ",", ".", ";", "᾽",
}


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_PUNC_RE = re.compile(r"[^\w\s\u0300-\u036f\u1f00-\u1fff]", re.UNICODE)


def tokenise(text: str) -> list[str]:
    """
    Split text into word tokens, stripping punctuation.

    We keep Unicode combining characters (diacritics) so polytonic Greek
    is not mangled. A Greek word like 'ἄνθρωπος' stays intact.
    """
    # Replace hyphens and em-dashes with spaces
    text = text.replace("—", " ").replace("-", " ")
    # Strip other punctuation (but not letters or diacritics)
    text = _PUNC_RE.sub(" ", text)
    return [tok.strip().lower() for tok in text.split() if tok.strip()]


# ---------------------------------------------------------------------------
# Lemmatisation
# ---------------------------------------------------------------------------

def _get_latin_lemmatiser():
    """Lazy import of CLTK's Latin BackoffLemmatizer."""
    try:
        from cltk.lemmatize import LatinBackoffLemmatizer
        return LatinBackoffLemmatizer()
    except ImportError:
        log.warning(
            "CLTK not installed. Latin lemmatisation unavailable; "
            "using raw word forms. Install with: pip install cltk"
        )
        return None


def _get_greek_lemmatiser():
    """Lazy import of CLTK's Greek BackoffLemmatizer."""
    try:
        from cltk.lemmatize import GreekBackoffLemmatizer
        return GreekBackoffLemmatizer()
    except ImportError:
        log.warning(
            "CLTK not installed. Greek lemmatisation unavailable; "
            "using raw word forms. Install with: pip install cltk"
        )
        return None


# Module-level cache so we only instantiate lemmatisers once per run.
_lemmatisers: dict = {}


def lemmatise(tokens: list[str], language: str) -> list[str]:
    """
    Return a list of lemmas corresponding to the input tokens.

    If CLTK is unavailable, returns tokens unchanged (raw forms).
    This degrades gracefully: the program still produces output, just
    with inflected forms instead of headwords in the vocabulary list.
    """
    
    # Normalise language codes from Tesserae ('la', 'grc') to full names
    language = {"la": "latin", "grc": "greek"}.get(language, language)

    if language not in _lemmatisers:
        if language == "latin":
            _lemmatisers[language] = _get_latin_lemmatiser()
        elif language == "greek":
            _lemmatisers[language] = _get_greek_lemmatiser()
        else:
            raise ValueError(f"Unknown language '{language}'.")

    lemmatiser = _lemmatisers.get(language)
    if lemmatiser is None:
        return tokens  # graceful fallback

    try:
        # CLTK's BackoffLemmatizer takes a list of tokens and returns
        # a list of (token, lemma) pairs.
        pairs = lemmatiser.lemmatize(tokens)
        return [lemma for (_tok, lemma) in pairs]
    except Exception as exc:
        log.debug("Lemmatisation failed: %s", exc)
        return tokens


# ---------------------------------------------------------------------------
# Frequency analysis and vocabulary selection
# ---------------------------------------------------------------------------

def build_vocab_list(
    lines: list[str],
    language: str,
    exclude_threshold: int = 10,
    progress_callback: Callable | None = None,
) -> list[str]:
    """
    Analyse a full text and return the vocabulary list for the facing page.

    The logic follows the Pharr method:
      - Count how often each lemma appears in the text.
      - Words that appear MORE than exclude_threshold times are assumed
        known (or learnable from repetition), so they're excluded.
      - Stop words are always excluded.
      - What remains is the 'facing vocabulary' — the words a student
        needs to look up.

    Args:
        lines:              All lines of the text.
        language:           'latin' or 'greek'
        exclude_threshold:  Words appearing >= this often are excluded.
                            Default 10, matching the original code.
        progress_callback:  Called with (current_line, total_lines).

    Returns:
        Sorted list of unique lemmas to include in the vocabulary.

    Why exclude high-frequency words?
      In Pharr's Aeneid, common words like 'arma' or 'que' are not glossed
      because a student at that level knows them. The threshold is the
      pedagogical judgment call. We expose it as a parameter.
    """
    stops = LATIN_STOPS if language == "latin" else GREEK_STOPS
    all_lemmas: list[str] = []
    total = len(lines)

    for i, line in enumerate(lines):
        if progress_callback:
            progress_callback(i + 1, total)
        tokens = tokenise(line)
        tokens = [t for t in tokens if t not in stops and len(t) > 1]
        lemmas = lemmatise(tokens, language)
        all_lemmas.extend(lemmas)

    counts = Counter(all_lemmas)

    vocab = sorted({
        lemma
        for lemma, count in counts.items()
        if count < exclude_threshold
        and lemma not in stops
        and len(lemma) > 1
    })

    log.info(
        "Vocabulary: %d unique lemmas, %d selected (threshold=%d)",
        len(counts), len(vocab), exclude_threshold,
    )
    return vocab


def get_page_vocab(
    chunk: str,
    full_vocab_list: list[str],
    language: str,
) -> list[str]:
    """
    For a given page chunk, return the subset of vocab_list that appears in it.

    This is called once per page when building the document.
    We lemmatise the chunk and intersect with the precomputed vocab list.

    Why not just look up every word on every page?
      Because the full vocabulary analysis happens once over the whole text.
      The exclude_threshold filtering needs the global word count to be
      meaningful. On a per-page basis we just ask: 'which words from our
      list appear here?'
    """
    stops = LATIN_STOPS if language == "latin" else GREEK_STOPS
    tokens = tokenise(chunk)
    tokens = [t for t in tokens if t not in stops and len(t) > 1]
    lemmas = lemmatise(tokens, language)
    # Intersect with the precomputed list, preserving alphabetical order
    page_lemmas = sorted(set(lemmas) & set(full_vocab_list))
    return page_lemmas
