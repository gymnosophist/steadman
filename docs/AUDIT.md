# Repository and artifact audit - 20 October 2026

## Result

The inner `steadman/steadman` directory is the real project checkout. Its HEAD
and GitHub `main` both resolved to
`204595f7e536aa8353283eca2830a646ba3d4b10` during the audit, confirmed with a
live HTTPS `git ls-remote` against https://github.com/gymnosophist/steadman .
There was no committed divergence. The differences were local staged work,
untracked files, and files stranded outside the checkout.

The package is now installable, the offline suite passes, the distributable
archives build, and sample PDFs render Latin and polytonic Greek correctly.
These checks establish software operation, not the correctness of every gloss.

## Initial state and comparison

GitHub's committed tree contained flat Python modules, `.gitignore`, `.Rhistory`,
a README, and third-party notices. It did not contain the package directory,
installation metadata, tests, fonts, or a code license file described in its README.

The local index already moved the entry point and five modules into `steadman/`,
replaced `corpus.py` with a longer version, added `restructure.sh`, deleted the
README and third-party notices, and repurposed the empty `.Rhistory` as a root
`__init__.py`. The other moved modules matched the committed contents before
this audit's fixes. The root initializer did not initialize the inner package.
Ten Gentium font files and two earlier lexicon backups were untracked.

The surrounding directory initially had a separate `.git` with no commits or remote,
alongside five generated PDFs, original tests and packaging metadata, and a
Claude handoff containing another proposed packaging fix. The outer repository
had not captured those artifacts in a commit. The initial audit inventoried
these files; the subsequent user-approved consolidation moved them into the
checkout as described below.

`docs/archive/initial-status.txt` and `initial-index.patch` preserve the original
staged work. The original migration script and two lexicon backups are also
retained there. They are historical references, not active application code.

## Changes made

- Established `steadman/__init__.py`; moved all ten fonts to the renderer's
  expected `steadman/fonts/` directory. Added the complete font license extracted
  verbatim from the supplied Gentium 7.000 font metadata.
- Adapted the existing handoff's packaging and MIT license. Corrected the project
  repository URL and declared core dependencies, CLI entry point, optional CLTK
  1.x and Whitaker's dependencies. Pinned Whitaker's to the tested upstream commit
  `92eb56f188ec9dadecca01ca34d3c9fd13d746da` (package 0.7.0).
- Replaced the misleading/deleted README with installation, behavior, tracking,
  accuracy, and certificate troubleshooting instructions. Restored third-party
  notices and identified the actual Whitaker's implementation and bundled fonts.
- Removed root `restructure.sh`; its original contents remain archived as text.
  The original script assumed flat modules and used `git add -A`.
- Normalized catalog language codes before passing works through the pipeline
  or selecting the GitHub text directory. The prior local code retained `la`
  while only mapping `latin`, which could route text retrieval incorrectly.
- Normalized Greek token text to NFC, so decomposed accents from live Tesserae
  texts match precomposed stop words and dictionary keys.
- Rejected nonpositive threshold/chunk-size arguments, corrected the inverted
  threshold explanation, and preserved explicitly supplied threshold 10 for
  partial works instead of silently overriding it with 3.
- Escaped poetry and titles before passing them to ReportLab, registered the
  bundled font family for bold vocabulary, and rejected mismatched chunk/vocab
  list lengths instead of silently dropping source chunks through `zip`.
- Removed cache directory creation at import time; caches are created when
  dictionary downloads are actually saved.
- Recovered/adapted tests from the outer folder and handoff. Replaced obsolete
  return-type expectations and a vacuous assertion with real frequency checks.
  Added corpus, CLI, Unicode, font, rendering-integrity, and pipeline regressions.
- Applied consistent formatting, import cleanup, and linting; added a GitHub
  Actions check definition for Python 3.10 and 3.12. This workflow has not run
  remotely because the changes have not been pushed.
- Added a SHA-256 artifact manifest and verifier. Generated PDFs, environments,
  caches, and temporary checks stay ignored. Source, fonts, licenses, and the
  historical evidence belong in Git; historical PDFs stay outside Git with their
  location, byte count, and hash recorded.

## Verification performed

Local runtime: Python 3.10.9 in an isolated `.venv`.

- 55 deterministic offline tests pass, including the CLI-to-PDF pipeline with
  controlled source/dictionary inputs. Tests deliberately disable CLTK models.
- Ruff lint and formatting checks pass for package, tests, and inventory tool.
- Editable installation and both command entry points (`steadman --help` and
  `python -m steadman --help`) work. Dependency consistency check passes.
- Both source distribution and wheel build successfully. Packaged font files
  and their license are included; archived backups, environments, generated
  PDFs, and runtime cache files are excluded.
- A two-page Latin/Greek sample was generated, extracted, rendered to PNGs,
  and visually inspected. Greek accents and bold headwords appear correctly.
- Live catalogs returned 1,834 Latin and 1,332 Greek entries. Live Latin and
  Greek `.tess` downloads succeeded, as did Lewis & Short and LSJ9 downloads.
- A live eight-line Aeneid sample passed through tokenization, frequency filtering,
  Whitaker's/fallback lookup, and PDF generation: 42 glosses for 46 selected words.
- The original 37 artifacts retained identical hashes through consolidation.
  The manifest now accounts for 60 files, including all inactive outer Git
  metadata files and the consolidation plan. The five historical PDFs retain
  unknown generation settings and source revisions. Fresh clones may skip
  absent local-only groups; missing files inside an existing group fail checks.

## Follow-up: consolidation and Greek alphabetical order

The user explicitly approved consolidating the surrounding folder. Twelve files
or directories were moved after checking the original manifest hashes:

- Five PDFs moved to `output/legacy/` (ignored; hashes tracked in the manifest).
- Claude handoff moved to `docs/archive/claude-handoff/`.
- Original README, notices, packaging file, tests, and empty R history moved to
  `docs/archive/pre-consolidation/`.
- The empty outer repository's complete `.git` moved to
  `.local-archive/outer-git/` (ignored and inactive). Preflight confirmed no commits,
  tracked files, or remotes. No Git metadata was discarded.

The exact source/destination mapping is in `docs/archive/consolidation-plan.json`.
Only the inner checkout is now an active Git repository. No source file or PDF
was discarded. The inventory now also detects unrecorded artifacts.

Greek vocabulary previously used raw Unicode sorting, separating accented vowels
from their expected alphabetic positions. `steadman/collation.py` now defines one
shared dictionary key used by full-text vocabulary analysis, page vocabulary,
final dictionary headword ordering, and the renderer. It ignores case, accents,
breathings, iota subscripts, punctuation, and homonym numbers for primary order,
normalizes final sigma to sigma, and sorts citation forms by the headword before
the comma. Displayed words and dictionary lookup keys are not modified. NFC and
NFD spellings share a key; other ties use the complete NFC spelling for stability.

Regression checks cover words across the Greek alphabet, mixed encodings, final
sigma, capitals, Latin macrons, citation forms, and actual CLI/rendering order.
The original linguistic quality findings below are separate and remain open.

## Remaining findings and practical limits

1. **Linguistic accuracy needs a separate review.** In the live run, `arma` was
   reconstructed as `armum, -i, n.` and LSJ9 returned the incomplete text
   `verbal noun of , with senses` for `λόγος`. These are reproducible quality
   defects in noun citation reconstruction and upstream short-gloss extraction.
   This audit does not certify their correctness. Existing frequency-based
   Latin sense ranking and accent-insensitive Greek matching also lack context.
2. **Catalog and text mirror differ.** The catalog's Homer, Hymns, Book 1 entry
   attempted `texts/grc/homer.hymns.tess`, which returned HTTP 404. The program
   reports that retrieval error, but not every catalog entry has been checked.
3. **Python TLS configuration needs attention on this machine.** Requests using
   its default certificate bundle could not verify Tesserae. Using
   `REQUESTS_CA_BUNDLE=/etc/ssl/cert.pem` succeeded with verification enabled;
   the system HTTPS client also succeeded. No certificate verification was disabled
   and no system trust configuration was changed.
4. **CLTK models were not installed or exercised.** Basic operation and fallback
   mode were tested; morphology quality with actual CLTK models remains unverified.
5. **The existing layout is text above two vocabulary columns.** It does not
   generate a complete English translation beside the original. Chunks start
   on new pages but dense vocabulary can spill onto more than one physical page.
   Missing dictionary results are currently omitted without an output report.
6. **The outer Git folder is now inactive.** After user approval, its complete
   metadata was moved to `.local-archive/outer-git/`. The live repository remains
   in its original inner location, so its remote, working changes, and environment
   continue to work. The parent directory contains only this checkout and OS metadata.
7. **Remote SSH authentication failed.** HTTPS was used for comparison; the configured
   SSH remote was preserved. Publishing will need working SSH credentials or a
   deliberate switch to HTTPS. Nothing was committed or pushed during this audit.

## Re-run

See the README for installation and checks. To verify the legacy inventory:

```sh
python scripts/inventory_artifacts.py --check
```

To deliberately refresh it after reviewing additions or edits:

```sh
python scripts/inventory_artifacts.py
```

Inspect the diff before committing. The audit repairs are intended to complete
the existing package reorganization while preserving its evidence and artifacts.
