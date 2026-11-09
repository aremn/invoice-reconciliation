"""Re-check the hand-written answer key in data/expected-results.json.

Independent of the application: this script imports nothing from app/. It reads the
reference tables and the invoice records that the images were rendered from, and checks
only arithmetic and ID links:
  - a matched result points to a purchase order of the same supplier and to its receipts;
  - expected = ordered quantity x agreed unit price, billed = invoice total,
    difference = billed - expected;
  - an unmatched result (duplicate, unresolved, failed) shows no expected amount;
  - a duplicate shares supplier ID + invoice number with the earlier document it names;
  - the summary counts and the recoverable total add up from the rows.
It does not decide statuses; those are stated by hand with the rule that gives them.

Usage:  python scripts/check_expected.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def check_row(row: dict, invoices: dict, pos: dict, receipts: list, problems: list) -> None:
    name = row["file_id"]
    inv = invoices[name]
    if row["status"] in ("reconciled", "discrepant"):
        po = pos[row["po_id"]]
        if po["supplier_id"] != inv["supplier_id"]:
            problems.append(f"{name}: {po['po_id']} belongs to another supplier")
        expected = po["quantity"] * po["unit_cents"]
        if row["expected_cents"] != expected:
            problems.append(f"{name}: expected should be {po['quantity']} x {po['unit_cents']} = {expected}")
        if row["billed_cents"] != inv["total_cents"]:
            problems.append(f"{name}: billed should be the invoice total {inv['total_cents']}")
        if row["difference_cents"] != inv["total_cents"] - expected:
            problems.append(f"{name}: difference should be {inv['total_cents'] - expected}")
        linked = [r["receipt_id"] for r in receipts if r["po_id"] == po["po_id"]]
        if row["receipt_ids"] != linked:
            problems.append(f"{name}: receipts for {po['po_id']} are {linked}")
        if row["count_as_payable"] is not True:
            problems.append(f"{name}: a matched invoice counts as payable")
    else:
        if row.get("expected_cents") is not None or row.get("difference_cents") is not None:
            problems.append(f"{name}: no expected amount or difference without a match")
        if row["count_as_payable"] is not False:
            problems.append(f"{name}: must not count as payable")
    if row["status"] == "duplicate":
        first = invoices[row["duplicate_of"]]
        if (first["supplier_id"], first["invoice_number"]) != (inv["supplier_id"], inv["invoice_number"]):
            problems.append(f"{name}: not the same supplier + invoice number as {row['duplicate_of']}")


def check_summary(rows: list, summary: dict, label: str, problems: list) -> None:
    counts = {status: 0 for status in summary["counts"]}
    for row in rows:
        counts[row["status"]] += 1
    if counts != summary["counts"]:
        problems.append(f"{label}: counts should be {counts}")
    recoverable = sum(r["difference_cents"] for r in rows if r["status"] == "discrepant" and r["difference_cents"] > 0)
    if recoverable != summary["recoverable_cents"]:
        problems.append(f"{label}: recoverable should be {recoverable}")
    payable = sum(1 for r in rows if r["count_as_payable"])
    if payable != summary["payable_invoices"]:
        problems.append(f"{label}: payable invoices should be {payable}")


def main() -> int:
    seed, added = load("tasks/invoices/seed.json"), load("data/additions.json")
    pos = {po["po_id"]: po for po in seed["purchase_orders"] + added["purchase_orders"]}
    receipts = seed["receipts"] + added["receipts"]
    invoices = {inv["file_id"]: inv for inv in seed["invoices"] + added["invoices"]}
    expected = load("data/expected-results.json")
    batch = [d["file_id"] for d in load("data/documents.json")["documents"]]

    problems: list[str] = []
    rows = expected["documents"]
    if [r["file_id"] for r in rows] != batch:
        problems.append("expected results must list the same documents, in the same order, as data/documents.json")
    for row in rows:
        check_row(row, invoices, pos, receipts, problems)
    check_summary(rows, expected["summary"], "summary", problems)

    # The supplied seed answer key must still hold for the seed rows.
    by_id = {r["file_id"]: r for r in rows}
    for seed_row in load("tasks/invoices/expected-seed-results.json"):
        for key, value in seed_row.items():
            if by_id[seed_row["file_id"]].get(key) != value:
                problems.append(f"{seed_row['file_id']}: differs from expected-seed-results.json on {key}")

    # After the reviewer correction: the invoice is checked with the corrected field.
    after = expected["after_correction"]
    fix = after["correction"]
    corrected = dict(invoices[fix["file_id"]])
    if corrected[fix["field"]] != fix["from"]:
        problems.append("correction: 'from' is not the value printed on the invoice")
    corrected[fix["field"]] = fix["to"]
    check_row(after["document"], {**invoices, fix["file_id"]: corrected}, pos, receipts, problems)
    rows_after = [after["document"] if r["file_id"] == fix["file_id"] else r for r in rows]
    check_summary(rows_after, after["summary"], "summary after correction", problems)

    for problem in problems:
        print("PROBLEM:", problem)
    print(f"checked {len(rows)} documents + 1 correction: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
