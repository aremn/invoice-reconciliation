"""Run the batch: extract every document, reconcile, save, print a table.

Usage:
    python -m app.run --mode live      # call the model (needs OPENAI_API_KEY), save responses to replay/
    python -m app.run --mode replay    # no key needed: use the saved responses
    add --reset to forget earlier reviewer corrections
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.config import DB_PATH, DOCUMENTS_FILE, REPLAY_DIR, ROOT
from app.extract import extract_invoice
from app.insight import build_insight
from app.money import format_cents
from app.notes import draft_notes
from app.reconcile import Finding, ReconResult, Status, reconcile_batch, summarize
from app.reference import ReferenceData, load_reference
from app.store import Store


def load_documents(path: Path = DOCUMENTS_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["documents"]


def recompute(store: Store, reference: ReferenceData) -> list[ReconResult]:
    """Reconcile every document from its effective fields (extraction + corrections) and save the results.

    Called after a batch run and again after every reviewer correction.
    """
    ready, failed = [], {}
    for doc in store.documents():
        file_id = doc["file_id"]
        fields = store.effective_fields(file_id)
        if fields is not None:
            ready.append((file_id, fields))
            continue
        ext = store.extraction(file_id)
        error = ext.error if ext is not None else "not extracted yet"
        failed[file_id] = ReconResult(file_id=file_id, status=Status.FAILED,
                                      findings=[Finding("extraction_failed", error)])
    reconciled = {r.file_id: r for r in reconcile_batch(ready, reference.purchase_orders, reference.receipts)}
    results = [reconciled.get(doc["file_id"]) or failed[doc["file_id"]] for doc in store.documents()]
    store.save_results(results)
    return results


def run_batch(
    mode: str,
    store: Store,
    documents: list[dict] | None = None,
    reference: ReferenceData | None = None,
    replay_dir: Path = REPLAY_DIR,
    root: Path = ROOT,
) -> list[ReconResult]:
    documents = load_documents() if documents is None else documents
    reference = load_reference() if reference is None else reference
    store.remove_documents_not_in([doc["file_id"] for doc in documents])
    for position, doc in enumerate(documents):
        image_path = root / doc["image"]
        sha = hashlib.sha256(image_path.read_bytes()).hexdigest() if image_path.exists() else None
        if store.save_document(doc["file_id"], position, doc["image"], sha):
            print(f"{doc['file_id']}: the image changed, earlier corrections were dropped")
        # extract_invoice never raises, so one bad document cannot stop the loop.
        store.save_extraction(extract_invoice(doc["file_id"], image_path, mode, doc.get("simulate"), replay_dir))
    results = recompute(store, reference)
    draft_notes(store, results, mode, replay_dir)
    return results


def print_report(store: Store, results: list[ReconResult]) -> None:
    def money(cents: int | None) -> str:
        return "-" if cents is None else format_cents(cents)

    print(f"{'document':<18} {'source':<18} {'status':<11} {'PO':<6} {'expected':>9} {'billed':>9} {'diff':>8}  findings")
    for r in results:
        label = store.extraction(r.file_id).label
        notes = " | ".join(f.message for f in r.findings)
        print(f"{r.file_id:<18} {label:<18} {r.status.value:<11} {r.po_id or '-':<6} "
              f"{money(r.expected_cents):>9} {money(r.billed_cents):>9} {money(r.difference_cents):>8}  {notes}")
    summary = summarize(results)
    counts = ", ".join(f"{name} {count}" for name, count in summary.counts.items())
    print(f"\n{counts}\nrecoverable overcharges: {format_cents(summary.recoverable_cents)}"
          f"   payable invoices: {summary.payable_invoices}")

    print()
    print("Draft notes (written by the model from the verified findings; drafts only):")
    for r in results:
        note = store.note(r.file_id)
        if note is not None:
            print(f"- {r.file_id} [{note.label}]: {note.text or 'NOTE FAILED: ' + note.error}")
    insight = build_insight(results)
    if insight is not None:
        print()
        print(f"Process insight: {insight.text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and reconcile the invoice batch.")
    parser.add_argument("--mode", choices=["live", "replay"], default="replay")
    parser.add_argument("--reset", action="store_true", help="forget earlier reviewer corrections")
    args = parser.parse_args()

    store = Store(DB_PATH)
    if args.reset:
        store.reset()
    results = run_batch(args.mode, store)
    print_report(store, results)
    store.close()


if __name__ == "__main__":
    main()
