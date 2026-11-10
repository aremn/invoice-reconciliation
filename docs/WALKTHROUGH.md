# Walkthrough

A written walkthrough of the approach and the findings (about five minutes to read).

## The problem in one example

We ordered 5 cables at $20.00 (purchase order PO-2) and received 5 (receipt RC-2). The supplier's
invoice INV-2 bills 5 at $24.00. Expected 5 × 2000 = 10000 cents, billed 12000, difference 2000:
a $20.00 overcharge to clarify. The app does this check for a batch of invoice images and gives a
reviewer a queue with the evidence.

## Who does what

| Step | Done by | Why |
|---|---|---|
| Read the seven fields from the image | model | Layouts differ; a model reads any layout without per-layout rules. |
| Check the answer has the right shape, turn "24.00" into 2400 cents | code (Pydantic) | A wrong shape must become a visible `failed`, not a guess. |
| Find the purchase order by supplier ID + PO ID | code | The rule is exact. No "closest" record is ever chosen. |
| Expected amount, difference, quantity checks, duplicates, status, totals | code | Arithmetic and decisions are never model output. |
| Write a 2–4 sentence draft note from the verified facts | model | Wording only. Code rejects a draft with an ID or number that is not in the facts. |
| Compare the image with the extracted fields, correct, decide | reviewer | The model can misread and does not know when it does. |

## The flow

1. `python -m app.run --mode replay` (or **Check all invoices** in the app) reads `data/documents.json`.
2. Each image goes to the model (`app/extract.py` through `app/llm.py`). In replay mode the saved
   real answer from `replay/` is used instead, so no key is needed.
3. The original extraction is saved in SQLite (`app/store.py`) and is never changed afterwards.
4. `app/reconcile.py` matches and calculates. Each document gets one status:
   `reconciled`, `discrepant`, `duplicate`, `unresolved` or `failed`.
5. `app/notes.py` drafts a note for every document that is not `reconciled` or `failed`.
6. The review page (`app/ui.py`) shows the queue. A correction is saved as a separate row, step 4
   runs again, and the page is redrawn. The state survives a restart.

## The batch

Nine documents: the four supplied seeds plus four added invoices and one unreadable document.

| Document | What it is for | Result |
|---|---|---|
| `clean` | everything agrees | reconciled |
| `wrong-price` | unit price above the agreed one | discrepant, +$20.00 |
| `short-receipt` | 5 billed, 4 received, amounts agree | discrepant, $0.00 |
| `duplicate` | same supplier and invoice number as `clean` | duplicate |
| `missing-reference` | no PO on the invoice; two POs have the same amount | unresolved |
| `supplier-conflict` | the PO belongs to another supplier | unresolved |
| `po-typo` | prints `P0-4` (digit zero), no such PO | see below |
| `unreadable` | a blurred, unreadable document | failed |
| `api-error` | simulated API failure, labelled as such | failed |

Totals on the model's raw answers: recoverable $25.00, 4 payable invoices.
After the reviewer correction of `po-typo`: recoverable $20.00, 3 payable invoices.

## Findings

1. **The model silently "fixed" a typo.** `po-typo` prints `P0-4`; the model returned `PO-4`, a
   purchase order that exists. The app matched it and reported a $5.00 overcharge with no warning.
   The hand-written answer key caught it. A stricter prompt, a higher image detail setting and a
   larger model all returned the same answer, so it is a documented limitation, not a fixed bug.
   It is also the correction demo: the reviewer types `P0-4`, the status becomes `unresolved` and
   the recoverable total drops by $5.00.
2. **The most frequent issue is the purchase-order reference** (missing, unknown or belonging to
   another supplier): 3 of 9 documents after the correction. Suggested improvement: ask suppliers
   to print the exact PO number and send invoices without a valid one back at intake. This is a
   count on a small simulated batch, and a discrepancy is a question to clarify, not proof of
   wrongdoing.
3. **Temperature 0 did not make the model repeatable.** The extracted fields were identical in
   three live runs, but a second live run reworded all six notes. Saved responses and a code
   check on every note matter more than the temperature setting.
4. **Tests written by AI had a gap that only a deliberate break showed.** All 30 first tests
   passed, also after undercharges were (wrongly) counted as recoverable. A test was added.
5. **My own checker was wrong once.** The note check rejected two correct notes because of a
   comma after a number. The batch output showed it immediately because a rejected note is
   printed with its reason.

## What I would do next

- Show a warning when an extracted ID contains look-alike characters (0/O, 1/I) - as a hint for
  the reviewer, not as a new matching rule.
- Use the saved reviewer corrections as a regression set for new prompts or models.
- Export the queue and keep a history of note drafts (optional items of the brief, not attempted).

## Try it

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m app.run --mode replay --reset
.venv/Scripts/python -m streamlit run app/ui.py
```

In the app: **Check all invoices** → choose `po-typo` → compare card 1 with card 2 → type `P0-4` into
"Order number (PO)" → **Save and check again** → restart the app and look again.
