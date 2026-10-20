# steadman

A command-line tool that generates **Pharr-style classical text readers** as PDFs, with facing vocabulary for Latin and Ancient Greek.

Named after the tradition of Clyde Pharr's annotated *Aeneid*: the conviction that a student should never need to leave the page to look up a word.

Texts come from the [Tesserae corpus](https://tesserae.caset.buffalo.edu/).

---

## Installation

```bash
git clone https://github.com/gymnosophist/steadman.git
cd steadman

# Core install (editable mode recommended for development)
pip install -e .

# Recommended extras
pip install -e ".[nlp]"     # CLTK lemmatisation (Latin and Greek)
pip install -e ".[latin]"   # Whitaker's Words, the primary Latin lexicon
pip install -e ".[dev]"     # pytest

# Everything at once
pip install -e ".[nlp,latin,dev]"
```

Requires Python 3.10 or later (developed and tested on 3.12).

**Font (optional but recommended).** Download [Gentium Plus](https://software.sil.org/gentium/) from SIL International and place the `.ttf` files in `steadman/fonts/`. Gentium Plus covers Latin and polytonic Greek in one typeface. Without it the tool falls back to Helvetica, which handles Latin but may not render polytonic Greek correctly.

---

## Usage

### Interactive mode (recommended for first use)

```bash
steadman
# or: python -m steadman
```

The menu asks you to:

1. Choose a language (Latin or Greek)
2. Browse the Tesserae catalogue and select a text
3. Choose prose or poetry mode

The PDF is written to the current directory.

### Scripted mode

```bash
# Prose: search the catalogue by author/title fragment
steadman --language latin --text catilinam --format prose

# Poetry, custom output path
steadman --language latin --text aeneid --format poetry --output aeneid_reader.pdf

# Greek, A4 paper
steadman --language greek --text iliad --format poetry --page-size a4

# Show more vocabulary (only omit words appearing 5+ times)
steadman --threshold 5
```

If a search matches several texts, an interactive menu lets you pick one.

### All options

```
--language, -l    latin or greek (default: show both, then ask)
--text, -t        Search query for author/title (default: browse menu)
--format, -f      prose or poetry (default: ask interactively)
--output, -o      Output PDF path (default: <author>_<title>.pdf)
--threshold, -n   Omit words appearing this many times or more (default: 10)
--page-size       letter or a4 (default: letter)
--chunk-size      Lines per page for poetry (default: 20),
                  words per page for prose (default: 150)
--verbose, -v     Enable debug logging
```

---

## How it works

The Pharr method: words that appear **fewer than N times** in a text are listed in a facing vocabulary column with dictionary forms and short glosses. Words appearing N or more times are assumed to be learned through repetition and are omitted.

**Pipeline**

1. **Corpus** (`corpus.py`): texts come from the Tesserae REST API, with a fallback to the raw `.tess` files on GitHub.
2. **NLP** (`nlp.py`): tokenisation, CLTK lemmatisation, and frequency analysis. Without CLTK the tool falls back to raw word forms.
3. **Lexicon** (`lexicon.py`): definitions, cached locally after first use.
   - *Greek:* [lsj9](https://github.com/ciscoriordan/lsj9) short definitions (abridged LSJ), with an accent-insensitive fallback for lemma/headword mismatches.
   - *Latin:* [Whitaker's Words](https://github.com/blagae/whitakers_words) first, then Lewis & Short as a fallback.
4. **Morphology** (`morphology.py`): reconstructs full citation forms (nouns, adjectives, verbs, deponents, irregulars). Macrons are excluded by design.
5. **Render** (`render.py`): the PDF is built with ReportLab.

### Known limitations

- **lsj9 data quality.** Roughly 4% of lsj9 short definitions are corrupted: a stranded dialect or grammar note appears in place of the English gloss. Steadman mitigates this with a small hand-corrected table of very common words and a filter that drops obviously stranded notes. The filter is not comprehensive; some bad entries (for example ταχύς, μέλας) still slip through. Treat Greek glosses with some care, and see `lexicon.py` for details.
- **Macrons** are not shown on Latin headwords.

---

## Project structure

```
steadman/
├── steadman/
│   ├── __init__.py
│   ├── __main__.py     # Entry point: python -m steadman / `steadman`
│   ├── cli.py          # Argument parsing, interactive menus
│   ├── corpus.py       # Tesserae catalogue and text fetching, chunking
│   ├── lexicon.py      # lsj9, Whitaker's Words, Lewis & Short lookup + cache
│   ├── morphology.py   # Citation-form reconstruction
│   ├── nlp.py          # Tokenisation, lemmatisation, frequency analysis
│   ├── render.py       # ReportLab PDF generation
│   └── fonts/          # Place Gentium Plus .ttf files here
├── tests/
│   └── test_lexicon.py
├── pyproject.toml
├── THIRD_PARTY_NOTICES.md
├── LICENSE
└── README.md
```

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Third-party data

Steadman fetches lexica and texts at runtime and does not redistribute them. Licences and attribution are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

MIT. See [LICENSE](LICENSE).
