"""Before-and-after comparisons worked out from names (A46)."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.documents import comparisons, versions
from backend.documents.comparisons import Side
from backend.storage.base import StorageItem

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def item(name, mime="image/jpeg"):
    return StorageItem(name, name, mime, 10, NOW - timedelta(days=3))


def entries(*names, mime=None):
    items = [
        item(n, mime or ("application/pdf" if n.endswith(".pdf") else "image/jpeg")) for n in names
    ]
    return comparisons.pair(versions.group(items), lambda i: i.mime_type.startswith("image/"))


def shown(*names, **kw):
    """Each card: a comparison as (title, before, after, labels), a file as its name."""
    return [
        (e.title, e.before.name, e.after.name, (e.before_label, e.after_label))
        if isinstance(e, comparisons.Comparison)
        else e.name
        for e in entries(*names, **kw)
    ]


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("Cozinha (antes)", ("Cozinha", Side.BEFORE, None)),
        ("Cozinha (depois)", ("Cozinha", Side.AFTER, None)),
        ("Cozinha(ANTES)", ("Cozinha", Side.BEFORE, None)),
        ("Cozinha ( depois )", ("Cozinha", Side.AFTER, None)),
        ("Cozinha (antes - Projeto)", ("Cozinha", Side.BEFORE, "Projeto")),
        ("Cozinha (depois – Obra pronta)", ("Cozinha", Side.AFTER, "Obra pronta")),
        ("Cozinha (antes: Render)", ("Cozinha", Side.BEFORE, "Render")),
        ("Cozinha (antes - )", ("Cozinha", Side.BEFORE, None)),  # an empty label is none
        ("Kitchen (before)", ("Kitchen", Side.BEFORE, None)),
        ("Kitchen (after - Built)", ("Kitchen", Side.AFTER, "Built")),
        ("Sala (2) (antes)", ("Sala (2)", Side.BEFORE, None)),
        # Not a marker: the word must be the bracket's start, at the name's end.
        ("Cozinha antes", None),
        ("Cozinha (antes) final", None),
        ("Cozinha (antigo)", None),
        ("(antes)", None),  # no title
        ("Cozinha (projeto antes)", None),
    ],
)
def test_a_marker_at_the_end_of_the_name_says_the_side_and_label(base, expected):
    found = comparisons.marked(base)
    assert (found and (found.title, found.side, found.label)) == expected


def test_two_images_of_one_title_are_one_comparison_in_the_befores_place():
    assert shown("Planta.pdf", "Cozinha (depois).jpg", "Fachada.jpg", "Cozinha (antes).png") == [
        "Planta.pdf",
        "Fachada.jpg",
        ("Cozinha", "Cozinha (antes).png", "Cozinha (depois).jpg", (None, None)),
    ]


def test_titles_pair_whatever_their_case_and_separators_and_keep_each_sides_label():
    assert shown("sala_estar (antes - Projeto).jpg", "Sala Estar (depois - Obra).jpg") == [
        (
            "sala_estar",
            "sala_estar (antes - Projeto).jpg",
            "Sala Estar (depois - Obra).jpg",
            ("Projeto", "Obra"),
        )
    ]


def test_portuguese_and_english_markers_pair_with_each_other():
    assert shown("Cozinha (antes).jpg", "Cozinha (after).jpg")[0][0] == "Cozinha"


def test_each_side_keeps_its_versions():
    [comparison] = entries("Cozinha (antes).jpg", "Cozinha (antes) v2.jpg", "Cozinha (depois).jpg")
    assert comparison.before.version == 2
    assert [i.name for _n, i in comparison.before.versions] == [
        "Cozinha (antes) v2.jpg",
        "Cozinha (antes).jpg",
    ]


@pytest.mark.parametrize(
    "names",
    [
        ["Cozinha (antes).jpg"],  # one side alone
        ["Cozinha (antes).jpg", "Cozinha (antes).png", "Cozinha (depois).jpg"],  # which before?
        ["Cozinha (antes).jpg", "Cozinha (depois).jpg", "Cozinha (depois - Obra).jpg"],
        ["Cozinha (antes).pdf", "Cozinha (depois).jpg"],  # only images compare
        ["Cozinha (antes).jpg", "Copa (depois).jpg"],  # another title
    ],
)
def test_unclear_or_incomplete_pairs_stay_plain_files(names):
    assert shown(*names) == [versions.parse(n).base + versions.parse(n).extension for n in names]


def test_a_side_with_a_version_clash_stays_apart_for_staff_to_rename():
    cards = shown("Cozinha (antes) v2.jpg", "Cozinha (antes)_v2.jpg", "Cozinha (depois).jpg")
    assert all(isinstance(card, str) for card in cards)


def test_a_clash_on_one_side_never_lets_another_file_stand_in_for_it():
    """The clashing "before" files are still candidates: the PNG beside them
    doesn't become the comparison's "before" just because they stand aside."""
    cards = shown(
        "Cozinha (antes).jpg",
        "Cozinha (antes) v2.jpg",
        "Cozinha (antes)_v2.jpg",
        "Cozinha (antes).png",
        "Cozinha (depois).jpg",
    )
    assert all(isinstance(card, str) for card in cards)


def test_a_marked_file_that_isnt_an_image_still_counts_as_a_side():
    cards = shown("Cozinha (antes).pdf", "Cozinha (antes).jpg", "Cozinha (depois).jpg")
    assert all(isinstance(card, str) for card in cards)


@pytest.mark.parametrize(
    ("title", "side", "label", "locale", "name"),
    [
        ("Cozinha", Side.BEFORE, None, "pt-BR", "Cozinha (antes)"),
        ("Cozinha", Side.AFTER, "Obra", "pt-BR", "Cozinha (depois - Obra)"),
        ("Kitchen", Side.AFTER, None, "en", "Kitchen (after)"),
    ],
)
def test_the_name_written_reads_back_as_the_same_side(title, side, label, locale, name):
    assert comparisons.base_name(title, side, label, locale) == name
    found = comparisons.marked(name)
    assert (found.title, found.side, found.label) == (title, side, label)


@pytest.mark.parametrize(
    ("label", "cleaned"),
    [
        (None, None),
        ("   ", None),
        ("Obra (pronta)", "Obra pronta"),  # a bracket would end the marker early
        ("Obra\n  pronta", "Obra pronta"),
        ("a/b", "ab"),
        ("x" * 60, "x" * comparisons.LABEL_MAX),
    ],
)
def test_a_label_is_cleaned_so_it_reads_back(label, cleaned):
    assert comparisons.clean_label(label) == cleaned


def test_renaming_a_side_keeps_each_versions_number_and_extension():
    [comparison] = entries("Cozinha (antes).jpg", "Cozinha (antes) v2.JPG", "Cozinha (depois).jpg")
    assert comparisons.renamed(comparison.before, "Copa (antes - Obra)") == [
        ("Cozinha (antes) v2.JPG", "Copa (antes - Obra) v2.JPG"),
        ("Cozinha (antes).jpg", "Copa (antes - Obra).jpg"),
    ]
    # Renamed so, the files still make one comparison of two versions.
    [again] = entries("Copa (antes - Obra) v2.JPG", "Copa (antes - Obra).jpg", "Copa (depois).jpg")
    assert (again.title, again.before.version, again.before_label) == ("Copa", 2, "Obra")
