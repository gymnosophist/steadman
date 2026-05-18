# steadman

A command-line tool for generating **Pharr-style classical text readers** with facing vocabulary, in PDF format.

Named after the tradition of Carl Pharr's annotated *Aeneid* — the conviction that a student should never need to leave the page to look up a word.

Supports **Latin** and **Ancient Greek** texts from the [Tesserae corpus](https://tesserae.caset.buffalo.edu/).

---

## Installation

```bash
# Clone the repo
git clone [https://github.com/gymnosophist/steadman.git](https://github.com/gymnosophist/steadman.git)
cd steadman

# Install (editable mode recommended for development)
pip install -e .

# With CLTK for lemmatisation (recommended):
pip install -e ".[nlp]"
```

**Font (optional but recommended):**
Download [Gentium Plus](https://software.sil.org/gentium/) from SIL International and place the `.ttf` files in `steadman/fonts/`. This font supports both Latin and polytonic Ancient Greek in the same typeface. Without it, the tool falls back to Helvetica, which handles Latin but may not render polytonic Greek correctly.

---

## Usage

### Interactive mode (recommended for first use)

```bash
python -m steadman
```

This launches an interactive menu:
1. Choose a language (Latin or Greek)
2. Browse the Tesserae catalog and select a text
3. Choose prose or poetry mode
4. The PDF is generated in the current directory

### Scripted mode

```bash
# Generate a facing-vocabulary PDF of Cicero's Catilinarians
python -m steadman --language latin --text "catilinam" --format prose

# Virgil's Aeneid, poetry mode, custom output path
python -m steadman --language latin --text "aeneid" --format poetry --output aeneid_reader.pdf

# Homer's Iliad, A4 paper
python -m steadman --language greek --text "iliad" --format poetry --page-size a4

# Show only words appearing fewer than 5 times (more vocab, fewer exclusions)
python -m steadman --threshold 5
```

### All options

```
--language, -l    latin or greek (default: ask interactively)
--text, -t        Search query for author/title (default: browse menu)
--format, -f      prose or poetry (default: ask interactively)
--output, -o      Output PDF path (default: author_title.pdf)
--threshold, -n   Frequency threshold for vocab exclusion (default: 10)
--page-size       letter or a4 (default: letter)
--chunk-size      Lines per page (poetry) or words per page (prose)
--verbose, -v     Enable debug logging
```

---

## How it works

The Pharr method: for a given text, words that appear **fewer than N times** are printed in a facing vocabulary column, with dictionary forms and brief definitions. Words appearing N or more times are assumed known from repetition and are omitted.

**Pipeline:**
1. **Corpus** — texts fetched live from the Tesserae REST API (no local files needed)
2. **NLP** — tokenised and lemmatised with CLTK's BackoffLemmatizer
3. **Lexicon** — definitions fetched from [Logeion](https://logeion.uchicago.edu) (Lewis-Short for Latin, Middle Liddell for Greek), cached locally after first lookup
4. **Render** — PDF built with ReportLab; two-column vocabulary layout; Gentium Plus font for Unicode support

---

## Project structure

```
steadman/
├── steadman/
│   ├── __init__.py
│   ├── __main__.py     # Entry point: python -m steadman
│   ├── cli.py          # Argument parsing, interactive menus, progress bars
│   ├── corpus.py       # Tesserae API: catalog and text fetching, chunking
│   ├── lexicon.py      # Logeion API: Lewis-Short and Middle Liddell lookup
│   ├── nlp.py          # Tokenisation, lemmatisation, frequency analysis
│   ├── render.py       # ReportLab PDF generation
│   └── fonts/          # Place Gentium Plus .ttf files here
├── tests/
│   ├── test_nlp.py
│   └── test_corpus.py
├── pyproject.toml
└── README.md
```

---

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Differences from the original

| Old (`steadman.py`) | New |
|---|---|
| Jupyter notebook workflow | `python -m steadman` CLI |
| Hardcoded local XML lexica | Logeion API with disk cache |
| Stale CSV text catalogs | Live Tesserae REST API |
| `python-docx` OOXML two-column hack | ReportLab `BalancedColumns` |
| Global state, everything in one class | Separate `corpus`, `lexicon`, `nlp`, `render` modules |
| Vendored `open_words` in repo | Standard pip dependency |
| Python 3.7 venv committed to repo | `pyproject.toml`, no committed venv |
| No tests | Pytest suite |

---

## License

MIT — see LICENSE.
