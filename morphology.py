"""
morphology.py — Reconstruct full dictionary-style headwords from
Whitaker's Words' internal roots/category/form codes.

Why this exists:
  Whitaker's Words stores LEMMAS AS BARE STEMS internally ('gladi', not
  'gladius'). For a Pharr-style facing vocabulary, students expect the
  traditional dictionary citation form instead:

      Noun:  gladius, -i, m.
      Verb:  cado, cadere, cecidi, casus

  Whitaker's does not store these citation forms directly, but it DOES
  store enough structured data (declension/conjugation number, gender,
  and the raw stem set) to reconstruct them deterministically for the
  regular paradigms. This module is exactly that reconstruction layer.

What this module does NOT do:
  - Mark vowel length (macrons). Whitaker's data doesn't carry this, and
    guessing is worse than omitting it. By agreement, this project ships
    without macrons (gladii, not gladiī).
  - Cover every irregular/defective verb perfectly. Common irregulars
    (sum, eo, fero, volo, nolo, malo) are hand-coded in
    _IRREGULAR_VERBS below. Anything not covered there or by the regular
    tables falls back to showing just the lemma stem, exactly as
    before — this module never raises or blocks the pipeline, it only
    upgrades what it confidently can.

Data shapes coming in from Whitaker's (see lexicon.py's investigation
for how these were derived empirically):

  Noun,  category = [declension, subtype], form = [gender, stem_type]
      roots = [nominative_singular_or_stem, oblique_stem, ...]

  Verb,  category = [conjugation, subtype], form = [TRANS|INTRANS|DEP|...]
      roots = [present_stem_a, present_stem_b, perfect_stem, supine_stem]
      ('-' in any slot means "not attested / not applicable" — e.g.
      semi-deponents and deponents have '-' for the perfect-active slot.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Noun declension endings
#
# Keyed by (declension, gender). Value is (nom_sg_ending_or_None, gen_sg_suffix).
#
# nom_sg_ending_or_None:
#   For 1st/2nd declension the nominative singular is regular enough to
#   build from the stem + ending. For 3rd declension, the nominative
#   singular is irregular by nature (that's WHY Whitaker's gives it to
#   us directly as roots[0]) — so we use roots[0] as-is instead of
#   building it, and these tables only supply the genitive suffix.
# ---------------------------------------------------------------------------

_NOUN_GENDER_LABEL = {
    "M": "m.",
    "F": "f.",
    "N": "n.",
    "C": "c.",   # common gender (e.g. dies, sacerdos)
    "X": "",     # unknown/unspecified — omit rather than guess
}

# (declension, subtype) -> genitive singular suffix to append to the stem.
# subtype distinguishes things like masc vs fem 1st declension (rare),
# i-stem vs consonant-stem 3rd declension, etc. Where subtype doesn't
# change the genitive ending, multiple subtypes map to the same value.
#
# This table covers the COMMON, productive subtypes — i.e. the ones a
# student will actually run into in classical prose/verse. It does NOT
# attempt every subtype Whitaker's distinguishes internally; in
# particular:
#   - Greek-origin declension variants (subtypes 6, 7, 8 across several
#     declensions: chelys, Plato, Achilles, etc.) keep their own Greek
#     genitive patterns that don't reduce to a single suffix cleanly.
#   - subtype 9 in any declension is Whitaker's bucket for abbreviations
#     and indeclinable proper nouns (praenomina like 'T.' for Titus).
# Both fall through to None below, and the caller displays the bare
# stem instead — exactly the pre-existing behaviour, just for a smaller
# slice of words than before this module existed.
_NOUN_GEN_SG_SUFFIX = {
    (1, 1): "ae",      # rosa, -ae
    (2, 1): "i",        # dominus, -i
    (2, 2): "i",        # bellum, -i (neuter 2nd, same genitive)
    (2, 3): "i",        # puer, ager, vir, -i
    (2, 4): "i",        # gladius, exitium, -i (-ius/-ium stems)
    (2, 5): "i",        # filius and other -ius nouns with this subtype code
    (3, 1): "is",       # rex, miles, civitas, sol, -is (consonant stem)
    (3, 2): "is",       # corpus, tempus, nomen, alumen, -is (neuter consonant stem)
    (3, 3): "is",       # navis, urbs, fames, -is (i-stem M/F)
    (3, 4): "is",       # mare, animal, cochlear, -is (neuter i-stem)
    (4, 1): "us",       # manus, exercitus, exitus, -us
    (4, 2): "us",       # genu, cornu, -us (neuter 4th)
    (5, 1): "ei",       # res, -ei
}


def _format_noun(lexeme) -> str | None:
    """
    Build 'lemma, gen.suffix, gender.' for a noun lexeme, or None if we
    don't have a confident reconstruction (caller should fall back to
    the bare stem in that case).
    """
    category = list(getattr(lexeme, "category", []) or [])
    form = list(getattr(lexeme, "form", []) or [])
    roots = list(getattr(lexeme, "roots", []) or [])

    if len(category) < 1 or not roots:
        return None

    declension = category[0]
    subtype = category[1] if len(category) > 1 else 1
    gender_code = form[0] if form else "X"

    gender_label = _NOUN_GENDER_LABEL.get(gender_code, "")
    gen_suffix = _NOUN_GEN_SG_SUFFIX.get((declension, subtype))

    if gen_suffix is None:
        return None  # unrecognised declension/subtype combo — don't guess

    # roots[0] is the form Whitaker's considers the headword stem/form.
    # For 1st/2nd declension this IS the bare stem (needs -us/-a/-um
    # added for a true nominative); for 3rd/4th/5th declension Whitaker's
    # already gives us the irregular nominative singular directly.
    if declension == 1:
        nominative = roots[0] + "a"
    elif declension == 2:
        # 2nd declension nominative varies (-us, -um, -er with no
        # additional vowel, etc.) enough that we trust roots[0] as
        # given UNLESS it looks like a bare consonant stem needing -us.
        # Whitaker's roots[0] for 2nd declension is generally already
        # the full nominative stem minus -us/-um; reconstruct minimally:
        if gender_code == "N":
            nominative = roots[0] + "um"
        else:
            nominative = roots[0] + "us"
    elif declension == 3:
        # 3rd declension nominative singular is inherently irregular
        # (rex, miles, mare, ...) — this is exactly why Whitaker's
        # gives it to us directly as roots[0], already complete.
        nominative = roots[0]
    elif declension == 4:
        # 4th declension: roots[0] is a bare stem ('man' for 'manus',
        # 'corn' for 'cornu') — needs an ending built, same as 1st/2nd.
        nominative = roots[0] + ("u" if gender_code == "N" else "us")
    elif declension == 5:
        # 5th declension: roots[0] is a bare stem ('r' for 'res', 'di'
        # for 'dies') — needs '-es' appended.
        nominative = roots[0] + "es"
    else:
        return None  # unknown declension number — don't guess

    # Oblique stem for the genitive suffix: roots[1] if present and
    # different from roots[0], else fall back to roots[0].
    oblique = roots[1] if len(roots) > 1 and roots[1] not in ("", "-") else roots[0]

    parts = [nominative, f"-{gen_suffix}"]
    headword = ", ".join(parts)
    if gender_label:
        headword += f", {gender_label}"
    return headword


# ---------------------------------------------------------------------------
# Verb principal parts
#
# Whitaker's roots for a regular verb are a 4-slot list:
#   [present_stem_variant_a, present_stem_variant_b, perfect_stem, supine_stem]
#
# We reconstruct the four traditional principal parts:
#   1st:  present active indicative 1sg   (amo)
#   2nd:  present active infinitive       (amare)
#   3rd:  perfect active indicative 1sg   (amavi)
#   4th:  supine / perfect passive ptc stem (amatus)
#
# Conjugation endings keyed by (conjugation, subtype).
# ---------------------------------------------------------------------------

# (conjugation, subtype) -> (pres_1sg_suffix, pres_inf_suffix)
_VERB_PRESENT_ENDINGS = {
    (1, 1): ("o", "are"),         # amo, amare
    (2, 1): ("eo", "ere"),         # moneo, monere
    (3, 1): ("o", "ere"),          # rego, regere
    (3, 4): ("io", "ere"),         # capio, capere (3rd -io verbs)
    (4, 1): ("io", "ire"),         # audio, audire
}

_DEPONENT_PRESENT_ENDINGS = {
    (1, 1): ("or", "ari"),         # hortor, hortari
    (2, 1): ("eor", "eri"),        # vereor, vereri
    (3, 1): ("or", "i"),           # loquor, loqui
    (3, 4): ("ior", "i"),          # patior, pati
    (4, 1): ("ior", "iri"),        # partior, partiri
}


def _format_verb(lexeme) -> str | None:
    """
    Build 'praesens, praesens-infinitive, perfectum, supinum' for a verb
    lexeme, or None if we don't have a confident reconstruction.

    For deponents (form contains 'DEP'), there is no active perfect —
    the 3rd principal part traditionally shown is the perfect deponent
    1sg ('hortatus sum'), built from the supine-slot stem (roots[3])
    + 'us sum'. Whitaker's stores deponent perfects in the same 4th
    root slot it would use for a supine in an active verb.
    """
    category = list(getattr(lexeme, "category", []) or [])
    form = list(getattr(lexeme, "form", []) or [])
    roots = list(getattr(lexeme, "roots", []) or [])

    if len(category) < 1 or len(roots) < 4:
        return None

    conjugation = category[0]
    subtype = category[1] if len(category) > 1 else 1
    is_deponent = "DEP" in form

    pres_stem = roots[0]
    perf_stem = roots[2]
    supine_stem = roots[3]

    if is_deponent:
        endings = _DEPONENT_PRESENT_ENDINGS.get((conjugation, subtype))
        if endings is None:
            return None
        pres_1sg_suffix, pres_inf_suffix = endings

        first = pres_stem + pres_1sg_suffix
        second = pres_stem + pres_inf_suffix

        if supine_stem in ("", "-"):
            return None  # can't build the perfect deponent without it
        third = f"{supine_stem}us sum"

        return f"{first}, {second}, {third}"

    # Active verb: standard four principal parts.
    endings = _VERB_PRESENT_ENDINGS.get((conjugation, subtype))
    if endings is None:
        return None
    pres_1sg_suffix, pres_inf_suffix = endings

    first = pres_stem + pres_1sg_suffix
    second = pres_stem + pres_inf_suffix

    parts = [first, second]

    if perf_stem not in ("", "-"):
        parts.append(perf_stem + "i")
    else:
        # No perfect attested (semi-deponent / defective) — stop here
        # rather than guess.
        return ", ".join(parts)

    if supine_stem not in ("", "-"):
        parts.append(supine_stem + "us")

    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Hand-coded irregulars
#
# Common irregular verbs whose principal parts don't follow any regular
# conjugation pattern closely enough to reconstruct from roots/category.
# Keyed by Whitaker's lemma stem (roots[0]) for the PRESENT stem, since
# that's the most stable lookup key across an irregular verb's forms.
# ---------------------------------------------------------------------------

_IRREGULAR_VERBS = {
    "s":      "sum, esse, fui, futurus",       # Whitaker's stem for sum is 's'
    "poss":   "possum, posse, potui",
    "e":      "eo, ire, ii, itus",
    "fer":    "fero, ferre, tuli, latus",
    "vol":    "volo, velle, volui",
    "nol":    "nolo, nolle, nolui",
    "mal":    "malo, malle, malui",
    "fi":     "fio, fieri, factus sum",
    "ed":     "edo, esse, edi, esus",
}


# ---------------------------------------------------------------------------
# Adjective endings — positive degree only
#
# We show the POSITIVE degree citation form, with however many endings
# the adjective class traditionally takes:
#   1st/2nd decl, regular:     albus, -a, -um
#   1st/2nd decl, -er stems:   pulcher, pulchra, pulchrum
#   3rd decl, one ending:      felix, felicis
#   3rd decl, two endings:     fortis, -e
#   3rd decl, three endings:   acer, acris, acre
#
# Comparative/superlative are NOT shown — Whitaker's gives us those
# stems too (roots[2], roots[3]) but Pharr-style facing vocabularies
# conventionally cite only the positive degree; a student who needs the
# comparative will see it inflected in the text and can reason from the
# positive entry.
#
# Keyed by (declension, subtype) from category — the same fields used
# for nouns, but adjectives have their own subtype numbering, derived
# empirically the same way as the noun/verb tables (see lexicon.py's
# investigation notes for the methodology).
# ---------------------------------------------------------------------------

def _format_adjective(lexeme) -> str | None:
    category = list(getattr(lexeme, "category", []) or [])
    roots = list(getattr(lexeme, "roots", []) or [])

    if len(category) < 1 or len(roots) < 2:
        return None

    declension = category[0]
    subtype = category[1] if len(category) > 1 else 1

    masc_form = roots[0]
    oblique = roots[1] if roots[1] not in ("", "-") else roots[0]

    if declension == 1 and subtype == 1:
        # Regular -us, -a, -um (albus, bonus, magnus...). roots[0] here
        # is the bare stem (e.g. 'alb'), needing the ending built.
        return f"{masc_form}us, -a, -um"

    if declension == 1 and subtype == 2:
        # -er stems (pulcher, miser, noster, sacer...). roots[0] is
        # already the full masculine citation form ('pulcher'); we
        # spell the fem/neut forms in full off the oblique stem rather
        # than trying to abbreviate the shared portion, since the point
        # of syncopation (pulchra vs miser-a) isn't predictable from the
        # stem alone.
        return f"{masc_form}, {oblique}a, {oblique}um"

    if declension == 3 and subtype == 1:
        # One-ending 3rd declension: felix, ingens, vetus...
        # roots[0] is the nominative (irregular, given as-is, same
        # reasoning as 3rd-declension nouns); roots[1] is the oblique
        # stem used for the genitive.
        return f"{masc_form}, {oblique}is"

    if declension == 3 and subtype == 2:
        # Two-ending 3rd declension: fortis, -e. roots[0] is the bare
        # stem here, needing both endings built.
        return f"{masc_form}is, -e"

    if declension == 3 and subtype == 3:
        # Three-ending 3rd declension: acer, acris, acre. roots[0] is
        # the full masc -er form; roots[1] is the bare stem shared by
        # the fem (-is) and neut (-e) forms.
        return f"{masc_form}, {oblique}is, {oblique}e"

    return None  # unrecognised declension/subtype — don't guess



# A handful of the most common irregular verbs — most importantly the
# copula 'sum' itself — are stored by Whitaker's with roots = [] : no
# stem at all, just a special-cased lexeme. This makes sense
# linguistically (sum/es/est/eram/fui/... don't share a single stem you
# could append endings to) but means our category/roots-based
# reconstruction in _format_verb() can never apply to them; there is
# nothing to key off of except the sense text itself.
#
# This table is intentionally small and matched on an exact, distinctive
# first-sense string Whitaker's uses for each of these lexemes. It is
# checked BEFORE the regular roots[0]-keyed _IRREGULAR_VERBS table,
# since rootless lexemes would otherwise never reach that table at all
# (there's no roots[0] to look up).
# ---------------------------------------------------------------------------

_ROOTLESS_VERB_SENSES = {
    ("to be, exist", "also used to form verb perfect passive tenses with NOM PERF PPL"):
        "sum, esse, fui, futurus",
    ("be", "willing;", "wish;"):
        "volo, velle, volui",
}


def _check_rootless_irregular(lexeme) -> str | None:
    senses = getattr(lexeme, "senses", None) or []
    roots = getattr(lexeme, "roots", None) or []
    if roots:
        return None  # has real roots, not one of these special cases
    if not senses:
        return None
    key = tuple(s.strip() for s in senses)
    return _ROOTLESS_VERB_SENSES.get(key)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def reconstruct_headword(lexeme) -> str | None:
    """
    Attempt to reconstruct a full dictionary-style headword for a
    Whitaker's Words lexeme.

    Returns None if we can't confidently reconstruct one — callers
    should fall back to the bare stem (roots[0]) in that case, exactly
    as the pipeline already did before this module existed. This
    function never raises; any unexpected shape just yields None.

    Returns, e.g.:
        Noun: 'gladius, -i, m.'
        Verb: 'cado, cadere, cecidi, casus'
        Deponent verb: 'hortor, hortari, hortatus sum'
        Irregular verb: 'sum, esse, fui, futurus'
        Adjective (1st/2nd): 'albus, -a, -um'
        Adjective (3rd, 2-ending): 'fortis, -e'
        Adjective (3rd, 3-ending): 'acer, acris, acre'
    """
    try:
        word_type = getattr(lexeme, "wordType", None)
        word_type_label = word_type.value if word_type else ""

        if word_type_label == "Verb":
            rootless = _check_rootless_irregular(lexeme)
            if rootless is not None:
                return rootless
            roots = list(getattr(lexeme, "roots", []) or [])
            if roots and roots[0] in _IRREGULAR_VERBS:
                return _IRREGULAR_VERBS[roots[0]]
            return _format_verb(lexeme)

        if word_type_label == "Noun":
            return _format_noun(lexeme)

        if word_type_label == "Adjective":
            return _format_adjective(lexeme)

        return None  # adverbs, prepositions, etc. — not covered yet

    except Exception as exc:
        log.debug("Headword reconstruction failed: %s", exc)
        return None
