"""Draft notes, the insight and the review page. No test calls the model."""
import json

import pytest
from streamlit.testing.v1 import AppTest

from app.config import ROOT
from app.insight import build_insight
from app.notes import build_facts, check_note, draft_notes
from app.reconcile import Status
from app.reference import load_reference
from app.run import recompute, run_batch
from app.store import Store

FACTS = "Invoice number: INV-2; supplier: S1\nMatched purchase order: PO-2\nOrdered: 5 x $20.00 = $100.00 expected"


def test_note_check_accepts_values_from_the_facts():
    assert check_note("Invoice INV-2, PO-2: 5 x $20.00 = $100.00.", FACTS) is None


@pytest.mark.parametrize("note, extra", [
    ("Invoice INV-2 should be matched to PO-3.", "PO-3"),
    ("The supplier owes $25.00 on PO-2.", "25.00"),
    ("About 10 units were billed on INV-2.", "10"),
])
def test_note_check_rejects_new_ids_and_numbers(note, extra):
    assert extra in check_note(note, FACTS)


def test_replayed_notes_use_only_verified_facts(tmp_path):
    store = Store(tmp_path / "review.sqlite")
    results = run_batch("replay", store)
    for result in results:
        note = store.note(result.file_id)
        if result.status in (Status.RECONCILED, Status.FAILED):
            assert note is None  # nothing verified to explain
            continue
        assert note.label == "replayed" and note.error is None, (result.file_id, note.error)
        assert check_note(note.text, build_facts(result, store.effective_fields(result.file_id))) is None
    store.close()


def test_unresolved_facts_contain_no_expected_amount(tmp_path):
    store = Store(tmp_path / "review.sqlite")
    result = {r.file_id: r for r in run_batch("replay", store)}["missing-reference"]
    facts = build_facts(result, store.effective_fields("missing-reference"))
    assert "there is no expected amount" in facts and "PO-1" not in facts and "PO-2" not in facts
    store.close()


def test_insight_counts_documents_per_cause(tmp_path):
    store = Store(tmp_path / "review.sqlite")
    run_batch("replay", store)
    store.add_correction("po-typo", "po_id", "P0-4")
    insight = build_insight(recompute(store, load_reference()))
    assert insight.cause == "po_reference"
    assert insight.documents == ("missing-reference", "supplier-conflict", "po-typo")
    store.close()


def test_review_page_correction_flow(tmp_path, monkeypatch):
    """Open the page, correct po_id of `po-typo` to the printed value, mark it reviewed, 'restart'."""
    db = tmp_path / "review.sqlite"
    monkeypatch.setenv("INVOICE_DB", str(db))
    monkeypatch.setattr("app.config.DB_PATH", db)

    # The first start checks all invoices with the saved answers and shows the list.
    page = AppTest.from_file(str(ROOT / "app" / "ui.py"), default_timeout=30).run()
    assert not page.exception
    assert {m.label: m.value for m in page.metric}["Overcharged in total"] == "$25.00"

    page.button(key="open-po-typo").click().run()  # open one invoice
    assert not page.exception and "more than we agreed" in page.subheader[0].value
    page.text_input(key="po-typo-po_id").set_value("P0-4")
    next(b for b in page.button if b.label == "Save and check again").click().run()
    assert not page.exception and "cannot find the order" in page.subheader[0].value

    page.checkbox(key="po-typo-reviewed").check()
    next(b for b in page.button if b.label == "Save").click().run()

    page.button(key="back").click().run()  # back to the list
    metrics = {m.label: m.value for m in page.metric}
    assert (metrics["Overcharged in total"], metrics["Invoices that can be paid"]) == ("$20.00", "3")

    # A new page on the same database file = the app after a restart.
    restarted = AppTest.from_file(str(ROOT / "app" / "ui.py"), default_timeout=30).run()
    assert {m.label: m.value for m in restarted.metric}["Overcharged in total"] == "$20.00"
    store = Store(db)
    assert store.extraction("po-typo").fields.po_id == "PO-4"  # original extraction kept
    assert json.loads(store.corrections("po-typo")[0]["new_value"]) == "P0-4"
    assert store.review("po-typo") == (True, "")
    store.close()
