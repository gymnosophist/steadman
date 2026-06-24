"""
cli.py — Command-line interface for steadman.

Design principles:
  1. Interactive menu for text selection (per the spec).
  2. All options are also available as flags so the tool can be scripted.
  3. Progress reporting at every slow step (network, lemmatisation, rendering).
  4. Clear error messages that explain what went wrong and how to fix it.

Usage examples:
  # Interactive mode (launches menus):
  python -m steadman

  # Scripted mode (no menus needed):
  python -m steadman --language latin --text cicero --format prose --output cat.pdf

  # Explicitly set the frequency threshold:
  python -m steadman --threshold 5

  # A4 paper size:
  python -m steadman --page-size a4
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ANSI colour helpers (degrade gracefully on Windows without colorama)
# ---------------------------------------------------------------------------

def _c(text: str, code: str) -> str:
    """Wrap text in ANSI colour code if stdout is a tty."""
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def bold(t): return _c(t, "1")
def cyan(t): return _c(t, "36")
def green(t): return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t): return _c(t, "31")


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------

def paginated_menu(
    items: list,
    display_fn,
    prompt: str = "Select",
    page_size: int = 20,
) -> object:
    """
    Display a paginated numbered menu and return the selected item.

    Args:
        items:      List of objects to choose from.
        display_fn: Called with each item to produce its display string.
        prompt:     Label shown at the selection prompt.
        page_size:  How many items per page.

    Why paginated?
      The Tesserae catalog has hundreds of texts. Printing all 400+
      at once is unusable. We paginate and let the user navigate.
    """
    if not items:
        print(red("No items to display."))
        return None

    page = 0
    total_pages = (len(items) - 1) // page_size + 1

    while True:
        start = page * page_size
        end = min(start + page_size, len(items))
        page_items = items[start:end]

        print()
        print(bold(f"  {prompt}  (page {page + 1}/{total_pages})"))
        print(f"  {'─' * 50}")
        for i, item in enumerate(page_items, start=start + 1):
            print(f"  {cyan(str(i).rjust(3))}.  {display_fn(item)}")
        print(f"  {'─' * 50}")
        print(f"  {yellow('n')} = next page   {yellow('p')} = prev page   "
              f"{yellow('q')} = quit")
        print()

        raw = input(f"  Enter number or command: ").strip().lower()

        if raw == "q":
            print(yellow("Exiting."))
            sys.exit(0)
        elif raw == "n":
            if page < total_pages - 1:
                page += 1
            else:
                print(yellow("  Already on the last page."))
        elif raw == "p":
            if page > 0:
                page -= 1
            else:
                print(yellow("  Already on the first page."))
        else:
            try:
                choice = int(raw)
                if 1 <= choice <= len(items):
                    return items[choice - 1]
                else:
                    print(red(f"  Please enter a number between 1 and {len(items)}."))
            except ValueError:
                print(red("  Invalid input. Enter a number, 'n', 'p', or 'q'."))


def ask(prompt: str, default: str = "", choices: list[str] | None = None) -> str:
    """
    Simple single-line prompt with optional default and constrained choices.
    """
    choices_str = f" [{'/'.join(choices)}]" if choices else ""
    default_str = f" (default: {default})" if default else ""
    while True:
        raw = input(f"  {prompt}{choices_str}{default_str}: ").strip()
        if not raw and default:
            return default
        if choices and raw.lower() not in [c.lower() for c in choices]:
            print(red(f"  Choose one of: {', '.join(choices)}"))
            continue
        return raw


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def progress_bar(current: int, total: int, label: str = "", width: int = 40) -> None:
    """
    Print an in-place progress bar.

    We write to stderr so it doesn't pollute stdout if the user is
    redirecting output. The bar uses carriage return to overwrite itself.
    """
    if total == 0:
        return
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * current / total)
    label_str = f" {label}" if label else ""
    print(
        f"\r  [{bar}] {pct:3d}%{label_str}",
        end="",
        flush=True,
        file=sys.stderr,
    )
    if current >= total:
        print(file=sys.stderr)  # newline at completion


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="steadman",
        description=(
            "Generate a Pharr-style reader PDF with facing vocabulary.\n"
            "Supports Latin and Ancient Greek texts from the Tesserae corpus."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m steadman
      (fully interactive — recommended for first use)

  python -m steadman --language latin --text cicero.in_catilinam --format prose
      (search for a text by name fragment)

  python -m steadman --threshold 5 --page-size a4 --output aeneid.pdf
      (custom threshold and paper size, interactive text selection)
        """,
    )

    p.add_argument(
        "--language", "-l",
        choices=["latin", "greek"],
        help="Filter catalog to this language (default: show both, then ask)",
    )
    p.add_argument(
        "--text", "-t",
        metavar="QUERY",
        help="Text to search for (author or title fragment). "
             "If multiple matches, an interactive menu is shown.",
    )
    p.add_argument(
        "--format", "-f",
        choices=["prose", "poetry"],
        default=None,
        help="Chunking mode: prose (by word count) or poetry (by line). "
             "Default: ask interactively.",
    )
    p.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Output PDF path. Default: '<author>_<title>.pdf' in current directory.",
    )
    p.add_argument(
        "--threshold", "-n",
        type=int,
        default=10,
        metavar="N",
        help="Exclude words that appear >= N times in the text (default: 10). "
             "Lower = more vocabulary shown. Higher = only rare words.",
    )
    p.add_argument(
        "--page-size",
        choices=["letter", "a4"],
        default="letter",
        help="Output page size (default: letter)",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Lines per page for poetry (default: 20), "
             "words per page for prose (default: 150). Override here.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging for debugging.",
    )

    return p


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    """
    Main workflow. Called by __main__.py after argument parsing.

    Steps:
      1. Fetch catalog
      2. Language selection (if not given)
      3. Text selection (menu or search filter)
      4. Format selection (if not given)
      5. Fetch text
      6. NLP: build full vocabulary list + token map
      7. Per-chunk: get page vocab, look up definitions
      8. Render PDF
    """
    from steadman import corpus, nlp, lexicon, render

    # ── 1. Language ──────────────────────────────────────────────────────
    language = args.language
    if not language:
        print()
        print(bold("  Welcome to Steadman — Classical Text Reader Generator"))
        print()
        language = ask("Language", choices=["latin", "greek"])

    # ── 2. Fetch catalog ─────────────────────────────────────────────────
    print(f"\n  {cyan('Fetching catalog from Tesserae...')}", end="", flush=True)
    try:
        catalog = corpus.fetch_catalog(language=language)
    except RuntimeError as exc:
        print(red(f"\n  Error: {exc}"))
        sys.exit(1)
    print(f" {green('done.')} ({len(catalog)} texts)")

    # ── 3. Text selection ────────────────────────────────────────────────
    selected_work = None

    if args.text:
        query = args.text.lower()
        matches = [
            w for w in catalog
            if query in w.author.lower() or query in w.title.lower()
        ]
        if not matches:
            print(red(f"\n  No texts matching '{args.text}'. Showing full catalog."))
            matches = catalog
        if len(matches) == 1:
            selected_work = matches[0]
            print(f"  Selected: {green(selected_work.display())}")
        else:
            selected_work = paginated_menu(
                matches,
                display_fn=lambda w: w.display(),
                prompt="Select a text",
            )
    else:
        selected_work = paginated_menu(
            catalog,
            display_fn=lambda w: w.display(),
            prompt="Select a text",
        )

    if not selected_work:
        sys.exit(1)

    # ── 4. Format ────────────────────────────────────────────────────────
    fmt = args.format
    if not fmt:
        print()
        fmt = ask(
            f"Format for {selected_work.title}",
            choices=["prose", "poetry"],
            default="prose",
        )

    chunk_size = args.chunk_size or (20 if fmt == "poetry" else 150)

    # ── 5. Output path ───────────────────────────────────────────────────
    if args.output:
        output_path = Path(args.output)
    else:
        safe_author = selected_work.author.replace(" ", "_").lower()
        safe_title = selected_work.title.replace(" ", "_").lower()
        output_path = Path(f"{safe_author}_{safe_title}.pdf")
    print(f"\n  Output: {cyan(str(output_path))}")

    # ── 6. Fetch text ────────────────────────────────────────────────────
    print(f"\n  {cyan('Fetching text...')}", end="", flush=True)
    try:
        lines = corpus.fetch_text(selected_work)
    except RuntimeError as exc:
        print(red(f"\n  Error: {exc}"))
        sys.exit(1)

    if not lines:
        print(red(
            f"\n  Error: no text lines were returned for '{selected_work.display()}'.\n"
            f"  The file may exist in the Tesserae repo but contain no parseable content.\n"
            f"  Try a different text, or check the .tess file format manually."
        ))
        sys.exit(1)

    print(f" {green('done.')} ({len(lines)} lines)")

    # ── 7. Vocabulary analysis ───────────────────────────────────────────
    print(f"\n  {cyan('Analysing vocabulary')} (this may take a minute for long texts)...")

    def vocab_progress(cur, tot):
        progress_bar(cur, tot, label="lemmatising")

    # For partial works (a single book), the whole-text frequency counts
    # are lower simply because there's less text — drop the threshold so
    # we don't exclude too many words.
    threshold = args.threshold
    if selected_work.part_num and args.threshold == 10:
        threshold = 3
        print(f"  (Using frequency threshold={threshold} for partial text; "
              f"override with --threshold)")

    # build_vocab_list returns (vocab_list, token_map):
    #   vocab_list  — sorted list of unique lemmas that passed the threshold
    #   token_map   — dict mapping lemma -> a representative inflected token
    #                 seen in the text, for use by lexicon.lookup_batch()
    #                 (Whitaker's Words needs the inflected form, not the
    #                 CLTK stem — see lexicon.py module docstring)
    vocab_list, token_map = nlp.build_vocab_list(
        lines,
        language=selected_work.language,
        exclude_threshold=threshold,
        progress_callback=vocab_progress,
    )
    print(f"  {len(vocab_list)} vocabulary items selected "
          f"({len(token_map)} with representative tokens).")

    # ── 8. Chunk and look up definitions ─────────────────────────────────
    chunks = list(corpus.chunk_lines(lines, chunk_size=chunk_size, mode=fmt))
    print(f"\n  {cyan('Looking up definitions')} ({len(chunks)} pages)...")

    vocab_by_chunk: list[dict] = []
    lemma_order_by_chunk: list[list[str]] = []
    total_chunks = len(chunks)

    for i, chunk in enumerate(chunks):
        progress_bar(i + 1, total_chunks, label="dictionary lookups")

        # get_page_vocab returns [(lemma, token), ...] — the lemma is the
        # CLTK grouping key, the token is the inflected form actually on
        # this page (the best form to hand to Whitaker's for lookup).
        page_pairs = nlp.get_page_vocab(chunk, vocab_list, selected_work.language)

        # Separate into parallel structures for lookup_batch:
        #   tokens      — what to look up in the dictionary
        #   cltk_lemmas — fallback keys for Lewis-Short if Whitaker's fails
        tokens = [token for (_lemma, token) in page_pairs]
        cltk_lemmas = {token: lemma for (lemma, token) in page_pairs}

        # lookup_batch returns {token: Entry}
        entries = lexicon.lookup_batch(
            tokens,
            language=selected_work.language,
            cltk_lemmas=cltk_lemmas,
        )

        # Re-key by lemma (not token) so the render layer can sort and
        # display entries alphabetically by dictionary headword.
        # Entry.lemma is the reconstructed citation form ('gladius, -i, m.')
        # after the morphology.py changes, so it's already display-ready.
        entries_by_lemma = {
            entry.lemma: entry
            for entry in entries.values()
        }
        vocab_by_chunk.append(entries_by_lemma)
        lemma_order_by_chunk.append(sorted(entries_by_lemma.keys()))

    # ── 9. Render PDF ────────────────────────────────────────────────────
    print(f"\n  {cyan('Rendering PDF...')}", end="", flush=True)

    render.build_pdf(
        chunks=chunks,
        vocab_by_chunk=vocab_by_chunk,
        lemma_order_by_chunk=lemma_order_by_chunk,
        output_path=output_path,
        title=selected_work.display(),
        mode=fmt,
        page_size=args.page_size,
    )

    print(f" {green('done.')}")
    print(f"\n  {bold('PDF saved to:')} {green(str(output_path))}\n")