"""Unit tests for app/reconcile.py.

The seed test uses the structured invoice records from seed.json as if they were a
perfect extraction, and compares with expected-seed-results.json from the starter
pack (the answer key is supplied, not produced by this app).
"""
import json

import pytest

from app.models import InvoiceFields
from app.reconcile import Status, find_duplicates, reconcile_batch, reconcile_invoice, summarize
from app.reference import DATA_DIR, load_reference

REF = load_reference()
FIELDS = list(InvoiceFields.model_fields)


def seed_invoices() -> list[tuple[str, InvoiceFields]]:
    raw = json.loads((DATA_DIR / "seed.json").read_text(encoding="utf-8"))["invoices"]
    return [(row["file_id"], InvoiceFields(**{k: row[k] for k in FIELDS})) for row in raw]


def by_id(results):
    return {r.file_id: r for r in results}


EXPECTED = json.loads((DATA_DIR / "expected-seed-results.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("expected", EXPECTED, ids=[e["file_id"] for e in EXPECTED])
def test_seed_matches_supplied_expected_results(expected):
    result = by_id(reconcile_batch(seed_invoices(), REF.purchase_orders, REF.receipts))[expected["file_id"]]
    assert result.status.value == expected["status"]
    for key in ("expected_cents", "billed_cents", "difference_cents", "count_as_payable"):
        if key in expected:
            assert getattr(result, key) == expected[key], key


def test_clean_invoice_links_intended_po_and_receipt():
    r = by_id(reconcile_batch(seed_invoices(), REF.purchase_orders, REF.receipts))["clean"]
    assert (r.po_id, r.receipt_ids) == ("PO-1", ["RC-1"])
    assert r.findings == []


def test_worked_example_wrong_price_cites_po_and_agreed_price():
    r = by_id(reconcile_batch(seed_invoices(), REF.purchase_orders, REF.receipts))["wrong-price"]
    assert (r.po_id, r.agreed_unit_cents, r.expected_cents, r.difference_cents) == ("PO-2", 2000, 10000, 2000)
    codes = [f.code for f in r.findings]
    assert codes == ["unit_price_mismatch", "amount_difference"]
    assert "PO-2" in r.findings[0].message


def test_missing_reference_is_not_matched_by_amount():
    # Same supplier, SKU, quantity and amount as PO-1/PO-2, but no PO number.
    r = by_id(reconcile_batch(seed_invoices(), REF.purchase_orders, REF.receipts))["missing-reference"]
    assert r.po_id is None and r.expected_cents is None and r.difference_cents is None
    assert [f.code for f in r.findings] == ["missing_po_reference"]


def test_duplicate_and_unresolved_are_excluded_from_totals():
    summary = summarize(reconcile_batch(seed_invoices(), REF.purchase_orders, REF.receipts))
    assert summary.counts == {"reconciled": 1, "discrepant": 1, "duplicate": 1, "unresolved": 1, "failed": 0}
    assert summary.recoverable_cents == 2000
    assert summary.payable_invoices == 2


def test_first_received_copy_is_the_original():
    invoices = seed_invoices()
    reordered = [invoices[2], invoices[0]]  # 'duplicate' file arrives before 'clean'
    assert find_duplicates(reordered) == {"clean": "duplicate"}


def test_duplicate_key_ignores_case_and_spaces():
    a = InvoiceFields(supplier_id="S1", invoice_number="INV-1")
    b = InvoiceFields(supplier_id=" s1", invoice_number="inv-1 ")
    assert find_duplicates([("a", a), ("b", b)]) == {"b": "a"}


def invoice(**overrides) -> InvoiceFields:
    base = dict(invoice_number="INV-9", supplier_id="S1", po_id="PO-1", sku="CAB-1",
                quantity=5, unit_cents=2000, total_cents=10000)
    base.update(overrides)
    return InvoiceFields(**base)


def run_one(inv: InvoiceFields):
    return reconcile_invoice("x", inv, REF.purchase_orders, REF.receipts)


def test_unknown_po_is_unresolved():
    r = run_one(invoice(po_id="PO-7"))
    assert r.status is Status.UNRESOLVED and r.findings[0].code == "unknown_po"


def test_po_from_another_supplier_is_unresolved():
    r = run_one(invoice(supplier_id="S2"))
    assert r.status is Status.UNRESOLVED and r.findings[0].code == "supplier_conflict"
    assert r.expected_cents is None


def test_sku_conflict_is_unresolved():
    r = run_one(invoice(sku="CAB-2"))
    assert r.status is Status.UNRESOLVED and r.findings[0].code == "sku_conflict"


def test_inconsistent_invoice_total_is_unresolved_not_discrepant():
    # e.g. the model misread the quantity: 6 x 20.00 != 100.00
    r = run_one(invoice(quantity=6))
    assert r.status is Status.UNRESOLVED
    assert r.findings[0].code == "billed_total_inconsistent"
    assert r.difference_cents is None


def test_billing_more_than_ordered_and_received():
    r = run_one(invoice(quantity=6, total_cents=12000))
    assert r.status is Status.DISCREPANT
    assert r.difference_cents == 2000  # billed 12,000 - expected 5 x 2,000
    assert [f.code for f in r.findings] == ["quantity_vs_ordered", "quantity_vs_received", "amount_difference"]


def test_undercharge_is_discrepant_but_not_recoverable():
    under = reconcile_invoice("under", invoice(unit_cents=1800, total_cents=9000),
                              REF.purchase_orders, REF.receipts)
    assert under.status is Status.DISCREPANT and under.difference_cents == -1000
    over = reconcile_invoice("over", invoice(invoice_number="INV-8", po_id="PO-2", unit_cents=2400, total_cents=12000),
                             REF.purchase_orders, REF.receipts)
    assert summarize([under, over]).recoverable_cents == 2000


def test_short_receipt_is_discrepant_even_when_amounts_agree():
    receipts = (REF.receipts[0].model_copy(update={"quantity": 4}),)
    r = reconcile_invoice("x", invoice(), REF.purchase_orders, receipts)
    assert r.status is Status.DISCREPANT
    assert r.difference_cents == 0
    assert [f.code for f in r.findings] == ["quantity_vs_received"]


def test_missing_receipt_counts_as_zero_received():
    r = reconcile_invoice("x", invoice(), REF.purchase_orders, receipts=())
    assert r.received_qty == 0 and r.receipt_ids == []
    assert "no receipt recorded for PO-1" in r.findings[0].message


def test_unreadable_field_leaves_invoice_unresolved():
    r = run_one(invoice(total_cents=None))
    assert r.status is Status.UNRESOLVED
    assert r.findings[0].code == "missing_fields"
