# Third-Party Data

## Whitaker's Words (Latin morphology and primary lexicon)

Steadman uses William Whitaker's WORDS Latin dictionary and morphological
analyzer, via [whitakers_words](https://github.com/blagae/whitakers_words)
.

William A. Whitaker (1936-2010) released WORDS as public domain software,
free for any use. The dictionary and program are maintained today as a
digital preservation effort by volunteer contributors.

## Lewis & Short (Latin fallback lexicon)

Steadman's Latin fallback definitions, used when Whitaker's Words has no
entry, come from [lewis-short-json](https://github.com/IohannesArnold/lewis-short-json),
a JSON conversion of:

Lewis, Charlton T.; Short, Charles. *A Latin Dictionary*. Perseus Project,
Tufts University, 1997 (rev. 2014).

The underlying 1879 dictionary text is in the public domain. The Perseus
Digital Library's digitization is licensed under
[CC BY-SA 3.0 US](https://creativecommons.org/licenses/by-sa/3.0/us/),
with funding from the National Endowment for the Humanities. Steadman
downloads this data at runtime and does not redistribute it.

## LSJ9 (Greek lexicon)

Steadman's Greek vocabulary glosses are sourced from
[LSJ9](https://github.com/ciscoriordan/lsj9) by Francisco Riordan, a
structured digitization of Liddell, Scott, and Jones, *A Greek-English
Lexicon*, 9th ed. (Oxford, 1940).

The base 1940 text is in the public domain. The OCR corrections, structured
parsing, and grammatical annotations that make up LSJ9 are
Copyright (c) 2026 Francisco Riordan, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode).
Steadman downloads `lsj9_short_defs.json` from that repository and caches it
locally, unmodified.

## Gentium fonts (bundled)

`steadman/fonts/` contains the unmodified Gentium 7.000 font files supplied
with this local project. Embedded metadata credits Copyright (c) 2003-2025
SIL Global, with Reserved Font Names "Gentium" and "SIL". The complete
SIL Open Font License 1.1 and copyright notice were extracted verbatim from
the font metadata into `steadman/fonts/OFL.txt`. These fonts retain that
license, independently of the project's MIT code license.

## Tesserae texts

Catalog metadata comes from the Tesserae API, and text content from
https://github.com/tesserae/tesserae/tree/master/texts . Source editions and
rights vary by work; consult each upstream text's provenance before
redistributing generated readers. The source texts are fetched at runtime.
