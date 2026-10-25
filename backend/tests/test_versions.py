"""Versions worked out from names (A25, plan section 12)."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.documents import versions
from backend.storage.base import StorageItem

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def item(name, days_ago=30, mime="application/pdf", item_id=None):
    return StorageItem(item_id or name, name, mime, 10, NOW - timedelta(days=days_ago))


def grouped(*names):
    return [
        (d.name, d.version, [i.name for _n, i in d.versions], d.clash)
        for d in versions.group([item(n) for n in names])
    ]


@pytest.mark.parametrize(
    ("name", "number"),
    [
        ("Planta.pdf", None),
        ("Planta v2.pdf", 2),
        ("Planta V12.pdf", 12),
        ("Planta_v02.pdf", 2),
        ("Planta-v3.pdf", 3),
        ("Planta (v4).pdf", 4),
        # Not clear tokens: they stay part of the name.
        ("Planta_final_v2_final.pdf", None),
        ("Planta v0.pdf", None),
        ("v2.pdf", None),
        ("Plantav2.pdf", None),
        ("Planta (2).pdf", None),
        ("Planta R03.pdf", None),
        ("Revisão.pdf", None),
        # Only "v" marks a version (Fabio, 25 Oct 2026).
        ("Planta rev B.pdf", None),
        ("Planta rev.3.pdf", None),
        ("Planta revisão 2.pdf", None),
    ],
)
def test_only_a_clear_version_at_the_end_counts(name, number):
    assert versions.parse(name).number == number


def test_versions_of_one_name_are_one_document_the_highest_current():
    assert grouped("Planta v2.pdf", "Planta.pdf", "Planta v3.pdf") == [
        ("Planta.pdf", 3, ["Planta v3.pdf", "Planta v2.pdf", "Planta.pdf"], False)
    ]


def test_the_highest_number_is_current_not_the_latest_upload():
    newest_v2 = item("Planta v2.pdf", days_ago=1)
    older_v3 = item("Planta v3.pdf", days_ago=20)
    (document,) = versions.group([newest_v2, older_v3])
    assert document.current is older_v3


def test_case_and_separators_dont_split_a_document():
    assert grouped("planta baixa.PDF", "Planta_Baixa_v2.pdf")[0][2] == [
        "Planta_Baixa_v2.pdf",
        "planta baixa.PDF",
    ]


def test_another_extension_is_another_document():
    assert [g[0] for g in grouped("Planta.pdf", "Planta v2.dwg")] == ["Planta.pdf", "Planta.dwg"]


def test_a_version_shows_from_v2_never_v1():
    assert grouped("Memorial.pdf", "Planta v2.pdf", "Corte v1.pdf") == [
        ("Memorial.pdf", None, ["Memorial.pdf"], False),
        ("Planta.pdf", 2, ["Planta v2.pdf"], False),
        ("Corte.pdf", None, ["Corte v1.pdf"], False),  # still its clean name
    ]


def test_two_files_claiming_one_version_are_never_merged_but_flagged():
    assert grouped("Planta.pdf", "Planta v2.pdf", "planta_v2.pdf", "Corte.pdf") == [
        ("Planta.pdf", None, ["Planta.pdf"], True),
        ("Planta v2.pdf", None, ["Planta v2.pdf"], True),
        ("planta_v2.pdf", None, ["planta_v2.pdf"], True),
        ("Corte.pdf", None, ["Corte.pdf"], False),
    ]


def test_an_unnumbered_original_and_a_v1_clash():
    assert all(clash for *_rest, clash in grouped("Planta.pdf", "Planta v1.pdf"))


def test_a_google_format_groups_by_the_name_the_page_shows():
    native = item("Memorial", mime="application/vnd.google-apps.document")
    (document,) = versions.group([native, item("Memorial v2.pdf")])
    assert (document.name, document.older[0][1]) == ("Memorial.pdf", native)


def test_atualizado_for_seven_days_after_a_new_version():
    def updated(days_ago, *names):
        items = [item(n, days_ago=days_ago if n == names[0] else 90) for n in names]
        return versions.group(items)[0].updated(NOW)

    assert updated(6, "Planta v2.pdf", "Planta.pdf")
    assert not updated(8, "Planta v2.pdf", "Planta.pdf")
    assert not updated(1, "Planta.pdf")  # a new file is not a new version
    assert updated(1, "Planta v2.pdf")  # v1 removed since: still a new version


def test_the_next_version_counts_every_file_of_that_name():
    documents = versions.group([item("Planta v2.pdf"), item("planta v2.pdf"), item("Planta.pdf")])
    assert versions.next_name(documents, documents[0]) == "Planta v3.pdf"
    single = versions.group([item("Planta baixa_v02.pdf")])
    assert versions.next_name(single, single[0]) == "Planta baixa v3.pdf"


def test_an_upload_kept_apart_joins_no_document():
    documents = versions.group([item("Planta.pdf"), item("Planta (2).pdf"), item("Corte v2.pdf")])
    assert versions.apart(documents, "planta.pdf") == "planta (3).pdf"
    assert versions.apart(documents, "Corte v3.pdf") == "Corte v3 (2).pdf"
    assert versions.apart(documents, "Fachada.pdf") == "Fachada.pdf"
    kept = versions.apart(documents, "Planta.pdf")
    assert versions.same_document(documents, kept) is None
