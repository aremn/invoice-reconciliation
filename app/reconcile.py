"""Reconciliation rules from tasks/invoices/domain.md.

Pure functions: no file access, no model calls. Matching, expected amounts, quantity
checks, duplicates and statuses are decided here and nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.models import InvoiceFields, PurchaseOrder, Receipt
from app.money import format_cents


class Status(str, Enum):
    RECONCILED = "reconciled"
    DISCREPANT = "discrepant"
    DUPLICATE = "duplicate"
    UNRESOLVED = "unresolved"
    FAILED = "failed"  # set by the pipeline when extraction itself failed


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


@dataclass
class ReconResult:
    file_id: str
    status: Status
    findings: list[Finding] = field(default_factory=list)
    po_id: str | None = None  # only set when the PO reference was matched
    receipt_ids: list[str] = field(default_factory=list)
    ordered_qty: int | None = None
    received_qty: int | None = None
    agreed_unit_cents: int | None = None
    expected_cents: int | None = None  # never set for unresolved or duplicate invoices
    billed_cents: int | None = None
    difference_cents: int | None = None  # billed - expected; positive = overcharge
    duplicate_of: str | None = None

    @property
    def count_as_payable(self) -> bool:
        return self.status in (Status.RECONCILED, Status.DISCREPANT)


REQUIRED_FIELDS = ("supplier_id", "invoice_number", "po_id", "sku", "quantity", "unit_cents", "total_cents")


def _norm(value: str | None) -> str | None:
    """Compare IDs ignoring case and surrounding spaces ('po-2 ' == 'PO-2')."""
    if value is None:
        return None
    return value.strip().upper() or None


def find_duplicates(invoices: list[tuple[str, InvoiceFields]]) -> dict[str, str]:
    """Map file_id -> file_id of the earlier invoice with the same supplier and invoice number.

    `invoices` must be in received order; the first one seen is treated as the original.
    Invoices without a supplier or invoice number cannot be checked and are skipped here
    (they end up unresolved because of the missing field).
    """
    first_seen: dict[tuple[str, str], str] = {}
    duplicates: dict[str, str] = {}
    for file_id, inv in invoices:
        supplier, number = _norm(inv.supplier_id), _norm(inv.invoice_number)
        if supplier is None or number is None:
            continue
        key = (supplier, number)
        if key in first_seen:
            duplicates[file_id] = first_seen[key]
        else:
            first_seen[key] = file_id
    return duplicates


def reconcile_invoice(
    file_id: str,
    inv: InvoiceFields,
    purchase_orders: tuple[PurchaseOrder, ...],
    receipts: tuple[Receipt, ...],
    duplicate_of: str | None = None,
) -> ReconResult:
    result = ReconResult(file_id=file_id, status=Status.UNRESOLVED, billed_cents=inv.total_cents)

    if duplicate_of is not None:
        result.status = Status.DUPLICATE
        result.duplicate_of = duplicate_of
        result.findings.append(Finding(
            "duplicate",
            f"Same supplier ({inv.supplier_id}) and invoice number ({inv.invoice_number}) as "
            f"'{duplicate_of}'. Not counted as payable or recoverable.",
        ))
        return result

    missing = [name for name in REQUIRED_FIELDS if getattr(inv, name) is None]
    if "po_id" in missing:
        result.findings.append(Finding(
            "missing_po_reference",
            "No purchase-order reference on the invoice. Not matched by amount or SKU.",
        ))
    other_missing = [name for name in missing if name != "po_id"]
    if other_missing:
        result.findings.append(Finding("missing_fields", "Missing or unreadable: " + ", ".join(other_missing)))
    if missing:
        return result

    # Match by supplier ID + PO ID only.
    candidates = [po for po in purchase_orders if _norm(po.po_id) == _norm(inv.po_id)]
    if not candidates:
        result.findings.append(Finding("unknown_po", f"{inv.po_id} is not in the purchase-order table."))
        return result
    if len(candidates) > 1:
        result.findings.append(Finding("ambiguous_po", f"{inv.po_id} matches more than one purchase order."))
        return result
    po = candidates[0]
    if _norm(po.supplier_id) != _norm(inv.supplier_id):
        result.findings.append(Finding(
            "supplier_conflict",
            f"{po.po_id} belongs to supplier {po.supplier_id}, but the invoice is from {inv.supplier_id}.",
        ))
        return result
    if _norm(po.sku) != _norm(inv.sku):
        result.findings.append(Finding(
            "sku_conflict", f"Invoice bills SKU {inv.sku}, but {po.po_id} is for SKU {po.sku}.",
        ))
        return result

    result.po_id = po.po_id

    # The invoice must agree with itself before we trust its total as the billed amount.
    line_cents = inv.quantity * inv.unit_cents
    if line_cents != inv.total_cents:
        result.findings.append(Finding(
            "billed_total_inconsistent",
            f"Invoice line {inv.quantity} x {format_cents(inv.unit_cents)} = {format_cents(line_cents)}, "
            f"but its total is {format_cents(inv.total_cents)}. Check the extracted values.",
        ))
        return result

    matched_receipts = [r for r in receipts if _norm(r.po_id) == _norm(po.po_id) and _norm(r.sku) == _norm(po.sku)]
    received = sum(r.quantity for r in matched_receipts)
    expected = po.quantity * po.unit_cents
    billed = inv.total_cents
    difference = billed - expected

    result.receipt_ids = [r.receipt_id for r in matched_receipts]
    result.ordered_qty = po.quantity
    result.received_qty = received
    result.agreed_unit_cents = po.unit_cents
    result.expected_cents = expected
    result.difference_cents = difference

    if inv.unit_cents != po.unit_cents:
        result.findings.append(Finding(
            "unit_price_mismatch",
            f"Billed {format_cents(inv.unit_cents)} per unit; {po.po_id} agrees {format_cents(po.unit_cents)}.",
        ))
    if inv.quantity != po.quantity:
        result.findings.append(Finding(
            "quantity_vs_ordered", f"Billed quantity {inv.quantity}; {po.po_id} ordered {po.quantity}.",
        ))
    if inv.quantity != received:
        source = ", ".join(result.receipt_ids) if matched_receipts else f"no receipt recorded for {po.po_id}"
        result.findings.append(Finding(
            "quantity_vs_received", f"Billed quantity {inv.quantity}; received {received} ({source}).",
        ))
    if difference != 0:
        kind = "overcharge" if difference > 0 else "undercharge"
        result.findings.append(Finding(
            "amount_difference",
            f"Billed {format_cents(billed)} - expected {format_cents(expected)} "
            f"({po.quantity} x {format_cents(po.unit_cents)}) = {format_cents(difference)} {kind}.",
        ))

    result.status = Status.DISCREPANT if result.findings else Status.RECONCILED
    return result


def reconcile_batch(
    invoices: list[tuple[str, InvoiceFields]],
    purchase_orders: tuple[PurchaseOrder, ...],
    receipts: tuple[Receipt, ...],
) -> list[ReconResult]:
    """Reconcile invoices in received order (needed to tell the original from its duplicate)."""
    duplicates = find_duplicates(invoices)
    return [
        reconcile_invoice(file_id, inv, purchase_orders, receipts, duplicates.get(file_id))
        for file_id, inv in invoices
    ]


@dataclass(frozen=True)
class Summary:
    counts: dict[str, int]
    recoverable_cents: int  # positive differences on discrepant invoices only
    payable_invoices: int


def summarize(results: list[ReconResult]) -> Summary:
    counts = {status.value: 0 for status in Status}
    for r in results:
        counts[r.status.value] += 1
    recoverable = sum(
        r.difference_cents for r in results
        if r.status is Status.DISCREPANT and r.difference_cents is not None and r.difference_cents > 0
    )
    return Summary(
        counts=counts,
        recoverable_cents=recoverable,
        payable_invoices=sum(1 for r in results if r.count_as_payable),
    )
