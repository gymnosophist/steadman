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

---------------------------------------------------------------------------
Tokens vs lemmas — why both are tracked from here on
---------------------------------------------------------------------------
CLTK's lemmatiser frequently returns a bare morphological STEM rather
than a true dictionary headword: 'languentibus' -> 'langu' instead of
'langueo'. That stem is fine as a grouping key for frequency counting
(the whole point of build_vocab_list), but it is NOT a safe key to hand
to Whitaker's Words or Lewis-Short for dictionary lookup — Whitaker's is
a morphological parser that expects the original inflected form and
works out the headword itself; handing it a bare stem just fails to
match (see lexicon.py's module docstring for the full investigation).

So this module now returns (token, lemma) pairs throughout, instead of
collapsing immediately to lemma-only lists. nlp.py still uses lemma for
counting and the exclude_threshold filter (that logic is unaffected),
but the ORIGINAL TOKEN for each surviving lemma is preserved so
lexicon.py can do an accurate dictionary lookup later.
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


def _normalise_lang(language: str) -> str:
    """Normalise Tesserae short codes to full language names."""
    return {"la": "latin", "grc": "greek"}.get(language.lower(), language.lower())


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

    NOTE: kept for backward compatibility and for callers that only need
    lemmas (e.g. simple frequency counting elsewhere). Prefer
    lemmatise_pairs() below when you also need to preserve the original
    token for dictionary lookup.
    """
    pairs = lemmatise_pairs(tokens, language)
    return [lemma for (_tok, lemma) in pairs]


def lemmatise_pairs(tokens: list[str], language: str) -> list[tuple[str, str]]:
    """
    Return a list of (original_token, lemma) pairs.

    This is the version the rest of the pipeline should use: it keeps
    the original inflected token around so lexicon.py can hand it to
    Whitaker's Words (a morphological parser) instead of a bare CLTK
    stem, which frequently fails to match anything (see lexicon.py's
    module docstring).
    """
    language = _normalise_lang(language)

    if language not in _lemmatisers:
        if language == "latin":
            _lemmatisers[language] = _get_latin_lemmatiser()
        elif language == "greek":
            _lemmatisers[language] = _get_greek_lemmatiser()
        else:
            raise ValueError(f"Unknown language '{language}'.")

    lemmatiser = _lemmatisers.get(language)
    if lemmatiser is None:
        # Graceful fallback: token IS the lemma.
        return [(tok, tok) for tok in tokens]

    try:
        pairs = lemmatiser.lemmatize(tokens)
        # CLTK already returns (token, lemma) pairs in this shape.
        return list(pairs)
    except Exception as exc:
        log.debug("Lemmatisation failed: %s", exc)
        return [(tok, tok) for tok in tokens]


# ---------------------------------------------------------------------------
# Frequency analysis and vocabulary selection
# ---------------------------------------------------------------------------

def build_vocab_list(
    lines: list[str],
    language: str,
    exclude_threshold: int = 10,
    progress_callback: Callable | None = None,
) -> tuple[list[str], dict[str, str]]:
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
        A tuple of:
          - Sorted list of unique lemmas to include in the vocabulary
            (same shape as before — callers that only used the old
            single-list return value can take vocab_list[0]).
          - A dict mapping lemma -> a representative original token
            seen in the text for that lemma. This is what lexicon.py
            should be given for dictionary lookup, NOT the lemma key
            itself (see nlp.py / lexicon.py module docstrings).

    Why exclude high-frequency words?
      In Pharr's Aeneid, common words like 'arma' or 'que' are not glossed
      because a student at that level knows them. The threshold is the
      pedagogical judgment call. We expose it as a parameter.

    Why track a representative token per lemma?
      Because CLTK's lemma is sometimes a bare stem ('langu') that
      Whitaker's Words cannot look up directly. We need a real inflected
      form ('languentibus') to hand to the dictionary layer. Any one
      occurrence will do — we just need ONE valid inflected form per
      lemma, and the first one encountered is as good as any other for
      this purpose.
    """
    language = _normalise_lang(language)
    stops = LATIN_STOPS if language == "latin" else GREEK_STOPS
    all_lemmas: list[str] = []
    # First token seen for each lemma — used later for dictionary lookup.
    lemma_to_token: dict[str, str] = {}
    total = len(lines)

    for i, line in enumerate(lines):
        if progress_callback:
            progress_callback(i + 1, total)
        tokens = tokenise(line)
        tokens = [t for t in tokens if t not in stops and len(t) > 1]
        pairs = lemmatise_pairs(tokens, language)
        for token, lemma in pairs:
            all_lemmas.append(lemma)
            if lemma not in lemma_to_token:
                lemma_to_token[lemma] = token

    counts = Counter(all_lemmas)

    vocab = sorted({
        lemma
        for lemma, count in counts.items()
        if count < exclude_threshold
        and lemma not in stops
        and len(lemma) > 1
    })

    # Trim the token map down to just the lemmas that survived filtering.
    vocab_tokens = {lemma: lemma_to_token[lemma] for lemma in vocab}

    log.info(
        "Vocabulary: %d unique lemmas, %d selected (threshold=%d)",
        len(counts), len(vocab), exclude_threshold,
    )
    return vocab, vocab_tokens


def get_page_vocab(
    chunk: str,
    full_vocab_list: list[str],
    language: str,
) -> list[tuple[str, str]]:
    """
    For a given page chunk, return the subset of vocab entries that
    appear in it, as (lemma, original_token) pairs.

    This is called once per page when building the document.
    We lemmatise the chunk and intersect with the precomputed vocab list,
    keeping the page's OWN original token for each lemma — a word may be
    inflected differently on different pages, and the token actually on
    this page is the most useful one to hand to the dictionary lookup,
    since it reflects exactly the form the student is looking at.

    Why not just look up every word on every page?
      Because the full vocabulary analysis happens once over the whole text.
      The exclude_threshold filtering needs the global word count to be
      meaningful. On a per-page basis we just ask: 'which words from our
      list appear here, and in what form?'
    """
    language = _normalise_lang(language)
    stops = LATIN_STOPS if language == "latin" else GREEK_STOPS
    tokens = tokenise(chunk)
    tokens = [t for t in tokens if t not in stops and len(t) > 1]
    pairs = lemmatise_pairs(tokens, language)

    vocab_set = set(full_vocab_list)
    # First token on THIS page for each lemma that's in our vocab list.
    page_map: dict[str, str] = {}
    for token, lemma in pairs:
        if lemma in vocab_set and lemma not in page_map:
            page_map[lemma] = token

    return sorted(page_map.items())
