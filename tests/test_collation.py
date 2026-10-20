"""Greek alphabetical order must follow letters rather than Unicode accents."""

import unicodedata
from unittest.mock import Mock

import pytest

from steadman import cli, corpus, lexicon, nlp, render
from steadman.collation import alphabetical_key

GREEK_ALPHABET_WORDS = [
    "ἀγαθός",
    "ἄνθρωπος",
    "βίος",
    "γῆ",
    "δῶρον",
    "εἰρήνη",
    "ζωή",
    "ἥλιος",
    "θάλασσα",
    "ἰδέα",
    "καί",
    "λόγος",
    "μήτηρ",
    "νῆσος",
    "ξένος",
    "ὁδός",
    "πᾶς",
    "ῥήτωρ",
    "σοφός",
    "τέχνη",
    "ὕδωρ",
    "φίλος",
    "χρόνος",
    "ψυχή",
    "ὥρα",
]


def test_polytonic_words_follow_greek_alphabet():
    assert sorted(reversed(GREEK_ALPHABET_WORDS), key=alphabetical_key) == GREEK_ALPHABET_WORDS


def test_equivalent_unicode_spellings_share_a_sort_key():
    for word in GREEK_ALPHABET_WORDS:
        assert alphabetical_key(word) == alphabetical_key(unicodedata.normalize("NFD", word))


def test_final_sigma_is_sorted_with_sigma():
    assert sorted(["σγ", "ςβ", "σα"], key=alphabetical_key) == ["σα", "ςβ", "σγ"]


@pytest.mark.parametrize("word", ["ἌΝΘΡΩΠΟΣ", "ἄνθρωπος", "ἀνθρωπος", "ανθρωπος"])
def test_case_and_breathings_do_not_change_primary_order(word):
    assert alphabetical_key(word)[0] == "ανθρωποσ"


def test_citation_suffixes_and_macrons_do_not_change_primary_order():
    assert alphabetical_key("ἀνήρ, ἀνδρός")[0] == alphabetical_key("ἀνήρ")[0]
    assert alphabetical_key("amō, amāre")[0] == "amo"
    assert sorted(["virtūs", "bellum", "amō"], key=alphabetical_key) == ["amō", "bellum", "virtūs"]


def test_homonym_numbers_and_punctuation_do_not_split_alphabetical_groups():
    assert alphabetical_key("λόγος2")[0] == alphabetical_key("λόγος")[0]
    assert alphabetical_key("ἀλλ᾽")[0] == alphabetical_key("ἀλλ")[0]


def test_analysis_and_page_vocabulary_use_the_same_order(monkeypatch):
    monkeypatch.setattr(nlp, "_lemmatisers", {"greek": None})
    words = ["ῥήτωρ", "ἄνθρωπος", "βίος", "ἀγαθός", "λόγος"]
    expected = ["ἀγαθός", "ἄνθρωπος", "βίος", "λόγος", "ῥήτωρ"]
    vocab, _ = nlp.build_vocab_list([" ".join(words)], "greek")
    assert vocab == expected
    assert [lemma for lemma, _ in nlp.get_page_vocab(" ".join(words), vocab, "greek")] == expected


def test_cli_orders_final_dictionary_headwords(monkeypatch, tmp_path):
    work = corpus.Work("test.tess", "Author", "Sample", "greek")
    monkeypatch.setattr(corpus, "fetch_catalog", lambda language: [work])
    monkeypatch.setattr(corpus, "fetch_text", lambda selected: ["λόγου βίου ἀνθρώπου"])
    monkeypatch.setattr(nlp, "_lemmatisers", {"greek": None})
    monkeypatch.setattr(
        lexicon,
        "lookup_batch",
        lambda *args, **kwargs: {
            "λόγου": lexicon.Entry("λόγος", short_def="word"),
            "βίου": lexicon.Entry("βίος", short_def="life"),
            "ἀνθρώπου": lexicon.Entry("ἄνθρωπος", short_def="human"),
        },
    )
    build = Mock()
    monkeypatch.setattr(render, "build_pdf", build)
    cli.run(
        cli.build_parser().parse_args(
            [
                "--language",
                "greek",
                "--text",
                "sample",
                "--format",
                "prose",
                "--output",
                str(tmp_path / "reader.pdf"),
            ]
        )
    )
    assert build.call_args.kwargs["lemma_order_by_chunk"] == [["ἄνθρωπος", "βίος", "λόγος"]]


def test_renderer_orders_direct_callers_vocabulary(monkeypatch):
    original = render.Paragraph
    paragraphs = []

    def record_paragraph(text, style):
        paragraph = original(text, style)
        paragraphs.append(paragraph.getPlainText())
        return paragraph

    monkeypatch.setattr(render, "Paragraph", record_paragraph)
    words = ["λόγος", "βίος", "ἄνθρωπος"]
    render._build_vocab_column(
        {word: lexicon.Entry(word, short_def="gloss") for word in words},
        words,
        render._build_styles(),
    )
    assert [text.split(":")[0] for text in paragraphs] == ["ἄνθρωπος", "βίος", "λόγος"]
