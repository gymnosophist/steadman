"""
render.py — PDF generation using ReportLab.

This replaces the python-docx approach. The key advantages:
  1. No dependency on Word or LibreOffice for PDF conversion.
  2. The two-column vocabulary layout is expressed in Python, not OOXML XML.
  3. Gentium Plus handles both Latin and polytonic Greek in the same font.
  4. Output is a single, portable PDF file.

Layout per page:
  ┌─────────────────────────────────────────┐
  │  [Title header]                          │
  ├─────────────────────────────────────────┤
  │  Latin/Greek text (full width)           │
  │  (12pt, paragraph or verse)             │
  ├────────────────┬────────────────────────┤
  │  ─────────────────────────────          │ (divider)
  │  Vocab col A   │  Vocab col B           │
  │  lemma: gloss  │  lemma: gloss          │
  └────────────────┴────────────────────────┘
  Page break between each chunk.

Font note:
  We embed Gentium Plus (SIL license, freely distributable), which
  covers Latin, polytonic Greek, Hebrew, and Coptic. If the font files
  are not present on the system, ReportLab falls back to Helvetica,
  which handles Latin but not polytonic Greek. We check for the font
  and warn the user if it's missing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Sequence

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    HRFlowable,
    BalancedColumns,
    KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from steadman.lexicon import Entry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Font registration
# ---------------------------------------------------------------------------

# Gentium Plus is available from SIL International.
# We look for it in a few common locations.
_GENTIUM_SEARCH_PATHS = [
    Path("/usr/share/fonts/truetype/gentium"),
    Path("/usr/share/fonts/gentium"),
    Path.home() / ".local/share/fonts",
    Path.home() / "Library/Fonts",
    Path("C:/Windows/Fonts"),
    Path(__file__).parent / "fonts",  # bundled with the package
]

_FONT_NAME = "Helvetica"   # fallback
_FONT_BOLD = "Helvetica-Bold"
_FONT_ITALIC = "Helvetica-Oblique"


def _try_register_gentium() -> tuple[str, str, str]:
    """
    Attempt to register Gentium Plus with ReportLab.

    Returns (regular, bold, italic) font name strings.
    If Gentium is found, returns ('GentiumPlus', 'GentiumPlus-Bold', ...).
    If not found, returns the Helvetica fallback tuple and logs a warning.
    """
    candidates = {
        "GentiumPlus": ["GentiumPlus-Regular.ttf", "GentiumPlus.ttf",
                        "gentiumplus-regular.ttf"],
        "GentiumPlus-Bold": ["GentiumPlus-Bold.ttf", "gentiumplus-bold.ttf"],
        "GentiumPlus-Italic": ["GentiumPlus-Italic.ttf",
                               "gentiumplus-italic.ttf"],
    }

    registered = {}
    for font_id, filenames in candidates.items():
        for search_dir in _GENTIUM_SEARCH_PATHS:
            for filename in filenames:
                path = search_dir / filename
                if path.exists():
                    try:
                        pdfmetrics.registerFont(TTFont(font_id, str(path)))
                        registered[font_id] = True
                        log.debug("Registered font '%s' from %s", font_id, path)
                        break
                    except Exception as exc:
                        log.debug("Failed to register %s: %s", path, exc)
            if font_id in registered:
                break

    if "GentiumPlus" in registered:
        regular = "GentiumPlus"
        bold = "GentiumPlus-Bold" if "GentiumPlus-Bold" in registered else "Helvetica-Bold"
        italic = "GentiumPlus-Italic" if "GentiumPlus-Italic" in registered else "Helvetica-Oblique"
        return regular, bold, italic
    else:
        log.warning(
            "Gentium Plus not found on this system. Using Helvetica as fallback.\n"
            "Polytonic Greek may not render correctly.\n"
            "Download Gentium Plus from: https://software.sil.org/gentium/\n"
            "And place the .ttf files in: %s",
            _GENTIUM_SEARCH_PATHS[-1],
        )
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


FONT_REGULAR, FONT_BOLD, FONT_ITALIC = _try_register_gentium()


# ---------------------------------------------------------------------------
# Style definitions
# ---------------------------------------------------------------------------

def _build_styles() -> dict[str, ParagraphStyle]:
    """
    Build the paragraph style dictionary.

    We define our own styles rather than modifying getSampleStyleSheet()
    so that multiple calls don't accumulate duplicate style registrations.
    """
    base = getSampleStyleSheet()
    styles = {}

    styles["text_body"] = ParagraphStyle(
        "text_body",
        fontName=FONT_REGULAR,
        fontSize=12,
        leading=16,      # line height: 12pt font + 4pt leading
        spaceAfter=4,
    )

    styles["text_verse"] = ParagraphStyle(
        "text_verse",
        fontName=FONT_REGULAR,
        fontSize=12,
        leading=16,
        spaceAfter=2,
        preserveNewlines=True,
    )

    styles["vocab_bold"] = ParagraphStyle(
        "vocab_bold",
        fontName=FONT_BOLD,
        fontSize=9,
        leading=12,
        spaceAfter=0,
    )

    styles["vocab_entry"] = ParagraphStyle(
        "vocab_entry",
        fontName=FONT_REGULAR,
        fontSize=9,
        leading=12,
        spaceAfter=2,
    )

    styles["title_style"] = ParagraphStyle(
        "title_style",
        fontName=FONT_BOLD,
        fontSize=14,
        leading=18,
        spaceAfter=12,
        alignment=1,  # centre
    )

    return styles


# ---------------------------------------------------------------------------
# Page content builders
# ---------------------------------------------------------------------------

def _build_text_block(chunk: str, mode: str, styles: dict) -> list:
    """
    Build the main text flowables for a page.

    For prose, we produce one Paragraph. For poetry, we produce one
    Paragraph per line so ReportLab handles line breaks correctly and
    doesn't reflow verse into prose.
    """
    flowables = []
    if mode == "poetry":
        for line in chunk.split("\n"):
            if line.strip():
                flowables.append(Paragraph(line.strip(), styles["text_verse"]))
            else:
                flowables.append(Spacer(1, 4))
    else:
        # Escape any angle brackets in the text so ReportLab doesn't
        # interpret them as XML tags.
        safe = chunk.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        flowables.append(Paragraph(safe, styles["text_body"]))
    return flowables


def _build_vocab_column(
    vocab_entries: dict[str, Entry],
    lemma_order: list[str],
    styles: dict,
) -> list:
    """
    Build the two-column vocabulary section as a list of flowables.

    Each entry is: BOLD LEMMA: plain gloss
    We pass the list to ReportLab's BalancedColumns, which handles the
    two-column layout automatically — no manual OOXML needed.
    """
    entries = []
    for lemma in lemma_order:
        entry = vocab_entries.get(lemma)
        if not entry:
            continue
        bold_part, plain_part = entry.format_vocab_entry()
        # Combine bold and plain in one Paragraph using inline markup
        safe_bold = bold_part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_plain = plain_part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = f"<b>{safe_bold}</b>{safe_plain}"
        entries.append(Paragraph(text, styles["vocab_entry"]))

    if not entries:
        return []

    # BalancedColumns splits its children across N columns.
    # This is the clean equivalent of the old OOXML sectPr/cols hack.
    return [
        HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=6),
        BalancedColumns(entries, nCols=2, spaceBefore=0),
    ]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def build_pdf(
    chunks: list[str],
    vocab_by_chunk: list[dict[str, Entry]],
    lemma_order_by_chunk: list[list[str]],
    output_path: str | Path,
    title: str = "",
    mode: str = "prose",
    page_size: str = "letter",
) -> None:
    """
    Render the complete Pharr-style PDF.

    Args:
        chunks:                One string per page of source text.
        vocab_by_chunk:        List of dicts (lemma → Entry) per chunk.
        lemma_order_by_chunk:  Sorted lemma lists per chunk (alphabetical).
        output_path:           Where to write the PDF.
        title:                 Title string for the first page header.
        mode:                  'poetry' or 'prose'.
        page_size:             'letter' or 'a4'.
    """
    output_path = Path(output_path)
    psize = A4 if page_size.lower() == "a4" else letter

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=psize,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=title,
    )

    styles = _build_styles()
    story = []

    if title:
        story.append(Paragraph(title, styles["title_style"]))
        story.append(Spacer(1, 0.2 * inch))

    total = len(chunks)
    for page_num, (chunk, vocab_entries, lemma_order) in enumerate(
        zip(chunks, vocab_by_chunk, lemma_order_by_chunk), start=1
    ):
        log.debug("Rendering page %d/%d", page_num, total)

        # Main text
        text_block = _build_text_block(chunk, mode, styles)
        story.extend(text_block)
        story.append(Spacer(1, 0.15 * inch))

        # Vocabulary
        vocab_block = _build_vocab_column(vocab_entries, lemma_order, styles)
        story.extend(vocab_block)

        # Page break between chunks (but not after the last one)
        if page_num < total:
            story.append(PageBreak())

    doc.build(story)
    log.info("PDF written to %s", output_path)
