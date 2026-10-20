# Third-Party Data

## Whitaker's Words (Latin morphology and primary lexicon)

Steadman uses William Whitaker's WORDS Latin dictionary and morphological
analyzer, via [whitakers_words](https://github.com/mk270/whitakers-words)
<!-- CONFIRM: swap in the actual Python port/repo Steadman depends on -->.

William A. Whitaker (1936-2010) released WORDS as public domain software,
free for any use. The dictionary and program are maintained today as a
digital preservation effort by volunteer contributors.

## Lewis & Short (Latin fallback lexicon)

Steadman's Latin fallback definitions, used when Whitaker's Words has no
entry, come from [lewis-short-json](https://github.com/IohannesArnold/lewis-short-json)
<!-- CONFIRM: swap in the actual repo Steadman depends on -->,
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