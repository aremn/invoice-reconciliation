"""One process-improvement insight, counted in code from the reconciliation results.

Findings are grouped into a few causes. The most frequent cause is reported together with
the documents that support it and a fixed suggestion. No model is involved.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.reconcile import ReconResult

# finding code -> cause
CAUSES = {
    "missing_po_reference": "po_reference",
    "unknown_po": "po_reference",
    "ambiguous_po": "po_reference",
    "supplier_conflict": "po_reference",
    "sku_conflict": "po_reference",
    "unit_price_mismatch": "price",
    "quantity_vs_ordered": "quantity",
    "quantity_vs_received": "quantity",
    "duplicate": "duplicate",
    "extraction_failed": "unreadable_or_failed",
    "missing_fields": "unreadable_or_failed",
    "billed_total_inconsistent": "unreadable_or_failed",
}

TEXT = {
    "po_reference": (
        "the purchase-order reference is missing, unknown or belongs to another supplier",
        "Ask suppliers to print the exact PO number, and send invoices without a valid one back at intake.",
    ),
    "price": (
        "the billed unit price differs from the agreed price",
        "Confirm the current price with the supplier when the order is placed, and clarify the difference before payment.",
    ),
    "quantity": (
        "the billed quantity differs from the ordered or received quantity",
        "Hold payment until the receipt is complete, or ask for an invoice for the delivered quantity.",
    ),
    "duplicate": (
        "the same supplier and invoice number arrived more than once",
        "Check supplier ID + invoice number at intake, before the invoice enters the queue.",
    ),
    "unreadable_or_failed": (
        "the document could not be read or the extracted values do not agree",
        "Ask for a clearer copy; these documents need manual entry by a reviewer.",
    ),
}


@dataclass(frozen=True)
class Insight:
    cause: str
    documents: tuple[str, ...]  # file_ids that support it
    total_documents: int
    text: str


def build_insight(results: list[ReconResult]) -> Insight | None:
    by_cause: dict[str, list[str]] = {}
    for result in results:
        for cause in {CAUSES[f.code] for f in result.findings if f.code in CAUSES}:
            by_cause.setdefault(cause, []).append(result.file_id)
    if not by_cause:
        return None
    # Most documents first; ties go to the cause listed first in TEXT.
    cause = max(TEXT, key=lambda name: len(by_cause.get(name, [])))
    documents = by_cause[cause]
    problem, suggestion = TEXT[cause]
    text = (
        f"Most frequent issue: {problem} - {len(documents)} of {len(results)} documents "
        f"({', '.join(documents)}). Suggested improvement: {suggestion} "
        "This is a count on a small simulated batch; a discrepancy is a question to clarify, not proof of wrongdoing."
    )
    return Insight(cause=cause, documents=tuple(documents), total_documents=len(results), text=text)
