# Steadman

Generate Latin and Ancient Greek reader PDFs with English vocabulary glosses.
The source text appears above two vocabulary columns on each page. This is a
vocabulary reader, not a parallel English translation.

## Install

Requires Python 3.10 or later. Run these commands from the directory containing
this README and `pyproject.toml` (the inner checkout if your folders are nested).

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
# Optional lemmatisation and Latin morphological dictionary:
python -m pip install -e '.[nlp,latin]'
# Development and verification:
python -m pip install -e '.[dev]'
```

CLTK 1.x supplies the BackoffLemmatizers used here. The optional dependency is
restricted to that API version and may require model downloads on first use. Without
CLTK, frequency counts use inflected word forms. Without Whitaker's Words,
Latin lookups use Lewis & Short, which cannot resolve every inflected form.
Fonts are included with their original SIL Open Font License.

## Use

```sh
python -m steadman --help
steadman
steadman --language latin --text catilinam --format prose --output reader.pdf
steadman --language greek --text iliad --format poetry --page-size a4
```

Language, text, and format are prompted when omitted. Multiple search matches
also open a selection menu. Text search matches author or title fragments.
Internet access is needed for catalog and text retrieval, and initially for
lexica; dictionaries are cached in the operating system's Steadman cache.

`--threshold N` excludes lemmas occurring **N or more times**. Raising N shows
more vocabulary; lowering it shows fewer words. Stop words are always excluded.
The default is 10, or 3 for a selected part/book; an explicit threshold always
wins. `--chunk-size N` sets words per chunk for prose (default 150) or lines for
poetry (default 20). Both options require positive integers. Chunks start on
new pages; dense vocabulary or long lines can overflow onto additional pages.

## Structure and tracking

- `steadman/`: importable package; CLI, corpus, NLP, lexicon, morphology, collation, renderer.
- `steadman/fonts/`: bundled Gentium 7.000 fonts and `OFL.txt`.
- `tests/`: deterministic tests which require no CLTK models or network.
- `scripts/`: reproducible artifact inventory tooling.
- `docs/AUDIT.md`: repository comparison, changes, verification, and limitations.
- `docs/artifact-manifest.json`: hashes and provenance of existing loose artifacts.
- `docs/archive/`: preserved migration script, initial Git status, old backups, Claude handoff,
  and original loose project files;
  excluded from release archives.
- `output/`, `tmp/`, virtual environments, caches, and generated PDFs: ignored.

Legacy PDFs now live in `output/legacy/`. The former outer Git directory is an
inactive backup at `.local-archive/outer-git/`; both directories are ignored by
Git. The surrounding folder now contains only this checkout (plus operating
system metadata). The original loose source files and Claude handoff are
preserved under `docs/archive/pre-consolidation/` and `docs/archive/claude-handoff/`.

The old root `restructure.sh` has been removed. Its original contents remain in
`docs/archive/restructure.sh.txt`. Do not run the archived script: it assumes the
former flat layout and stages unrelated files.

## Verification

```sh
python -m pytest
python -m pip install ruff build
ruff check steadman tests scripts
ruff format --check steadman tests scripts
python -m build
python scripts/inventory_artifacts.py --check
```

The inventory records 60 retained artifacts, including fonts, source archives,
legacy PDFs, and the inactive Git metadata. It preserves original paths and
SHA-256 hashes. PDFs and inactive Git metadata remain local; the other artifacts
are tracked. A fresh clone can skip absent local-only groups, while missing files
within an existing group fail verification. The old PDFs' source revisions and
generation settings remain unknown.

Vocabulary uses dictionary alphabetical order throughout analysis and rendering.
Greek accents, breathing marks, iota subscripts, capitalization, punctuation, and
homonym numbers do not affect primary order; final sigma sorts with sigma.
Displayed spellings remain unchanged. Citation forms after commas do not change
the headword's position. Equivalent Unicode encodings share the same sort key.

## Accuracy limits

Glosses are dictionary suggestions, not context-aware translations. Latin sense
selection uses dictionary frequency, not sentence context. Greek accent-stripped
matching can be ambiguous, and the LSJ9 source contains some malformed short
definitions. A small correction table and filter catch some errors; human review
is still needed. Missing dictionary results are omitted from the PDF.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for data and font attribution.
Code is MIT licensed; see [LICENSE](LICENSE).

### HTTPS troubleshooting on this machine

The installed Python certificate bundle rejected the Tesserae certificate chain
during this audit. The same requests succeeded with macOS's system bundle:

```sh
REQUESTS_CA_BUNDLE=/etc/ssl/cert.pem steadman --language latin --text catilinam --format prose
```

This keeps certificate verification enabled. The path is platform-specific;
other machines may work without an override.
