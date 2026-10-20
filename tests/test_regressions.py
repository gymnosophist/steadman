"""Regression checks for packaging, corpus routing, and reader integrity."""

from unittest.mock import Mock

import pytest

from steadman import corpus, lexicon, render
from steadman.cli import build_parser


@pytest.mark.parametrize("language,code", [("latin", "la"), ("greek", "grc")])
def test_catalog_normalizes_language(monkeypatch, language, code):
    response = Mock()
    response.json.return_value = [
        {"id": "author.work.tess", "author": "Author", "title": "Work", "language": code},
        {"id": "other.work.tess", "language": "unrelated"},
    ]
    monkeypatch.setattr(corpus.requests, "get", Mock(return_value=response))
    works = corpus.fetch_catalog(language)
    assert len(works) == 1
    assert works[0].language == language


@pytest.mark.parametrize("language,directory", [("la", "la"), ("grc", "grc"), ("greek", "grc")])
def test_text_routing_and_part_filter(monkeypatch, language, directory):
    response = Mock(text="<auth. 1.1> First book\n<auth. 2.1> Second book\ninvalid > skip")
    get = Mock(return_value=response)
    monkeypatch.setattr(corpus.requests, "get", get)
    work = corpus.Work("author.work.part.2.tess", "Author", "Work", language, part_num="2")
    assert corpus.fetch_text(work) == ["Second book"]
    assert get.call_args.args[0] == f"{corpus.GITHUB_RAW}/{directory}/author.work.tess"


@pytest.mark.parametrize("size", [0, -1])
def test_chunk_size_must_be_positive(size):
    with pytest.raises(ValueError, match="positive"):
        list(corpus.chunk_lines(["arma virumque"], size, "prose"))


@pytest.mark.parametrize("option", ["--chunk-size", "--threshold"])
@pytest.mark.parametrize("value", ["0", "-5"])
def test_cli_rejects_invalid_sizes(option, value):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([option, value])
    assert exc.value.code == 2


def test_explicit_default_threshold_is_preserved():
    assert build_parser().parse_args([]).threshold is None
    assert build_parser().parse_args(["--threshold", "10"]).threshold == 10


def test_renderer_refuses_to_drop_unmatched_chunks(tmp_path):
    with pytest.raises(ValueError, match="matching"):
        render.build_pdf(["one", "two"], [{}], [[]], tmp_path / "reader.pdf")


def test_poetry_and_titles_are_plain_text():
    blocks = render._build_text_block("arma <unknown> & virumque", "poetry", render._build_styles())
    assert blocks[0].getPlainText() == "arma <unknown> & virumque"


def test_bundled_greek_font_and_bold_variant():
    assert render.FONT_REGULAR == "GentiumPlus"
    from reportlab.lib.fonts import tt2ps
    from reportlab.pdfbase.pdfmetrics import getFont

    assert "Gentium" in getFont(render.FONT_REGULAR).face.name.decode()
    assert tt2ps(render.FONT_REGULAR, 1, 0) == render.FONT_BOLD


def test_greek_lookup_uses_lemma_and_filters_bad_gloss(monkeypatch):
    monkeypatch.setattr(
        lexicon, "_load_ml", lambda: ({"λόγος": "word, speech", "κακός": "Att. gen. dat"}, {})
    )
    assert lexicon.lookup("λόγου", "greek", cltk_lemma="λόγος").short_def == "word, speech"
    assert lexicon.lookup("κακός", "greek") is None


def test_greek_combining_accents_match_precomposed_words():
    import unicodedata

    from steadman.nlp import tokenise

    assert tokenise(unicodedata.normalize("NFD", "καί ἄνθρωπος")) == ["καί", "ἄνθρωπος"]


def test_cli_pipeline_writes_reader_and_keeps_explicit_threshold(tmp_path, monkeypatch):
    from steadman import cli, nlp

    work = corpus.Work("author.work.part.1.tess", "Author", "Sample", "latin", part_num="1")
    monkeypatch.setattr(corpus, "fetch_catalog", lambda language: [work])
    monkeypatch.setattr(corpus, "fetch_text", lambda selected: ["arma virumque cano"])
    monkeypatch.setattr(nlp, "_lemmatisers", {"latin": None})
    analyse = Mock(wraps=nlp.build_vocab_list)
    monkeypatch.setattr(nlp, "build_vocab_list", analyse)
    monkeypatch.setattr(
        lexicon,
        "lookup_batch",
        lambda tokens, **kwargs: {
            token: lexicon.Entry(token, short_def="test gloss") for token in tokens
        },
    )
    output = tmp_path / "reader.pdf"
    args = build_parser().parse_args(
        [
            "--language",
            "latin",
            "--text",
            "sample",
            "--format",
            "poetry",
            "--threshold",
            "10",
            "--output",
            str(output),
        ]
    )
    cli.run(args)
    assert analyse.call_args.kwargs["exclude_threshold"] == 10
    assert output.read_bytes().startswith(b"%PDF-")
