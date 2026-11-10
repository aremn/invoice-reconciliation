# Invoice Reconciliation & Review

Take-home assignment B: a small local platform that reads supplier invoices, matches them to
purchase orders and receipts, checks the amounts in code, and gives a reviewer a queue to
inspect, correct and re-run.

Short walkthrough: `docs/WALKTHROUGH.md`. What went wrong during the work: `docs/DEVLOG.md`.

## Setup

Python 3.11.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # on Linux/macOS: .venv/bin/python
cp .env.example .env   # then set OPENAI_API_KEY (only needed for live model calls)
```

## Run

```bash
.venv/Scripts/python -m pytest -q
```

Run the batch (extract → validate → match → calculate → save to SQLite → print a table):

```bash
.venv/Scripts/python -m app.run --mode replay          # no key needed, uses saved responses
.venv/Scripts/python -m app.run --mode live            # calls the model, re-records replay/
.venv/Scripts/python -m app.run --mode replay --reset  # also forget reviewer corrections
```

Each row is labelled `live`, `replayed` or `simulated-failure`. State is kept in
`state/review.sqlite` (not committed; set `INVOICE_DB` to use another file).

The batch output also prints the draft discrepancy notes and one process insight.

Review app:

```bash
.venv/Scripts/python -m streamlit run app/ui.py
```

It is written for a reviewer who is not a programmer and has two screens, like a mailbox:

1. **The list.** Every invoice is one row: its number and supplier, a coloured label and one
   sentence about the result ("The supplier asks for $20.00 more than we agreed."). Buttons above
   the list filter by status and show the counts. On the first start the app checks all invoices
   with the saved model answers, so there is nothing to press first.
2. **One invoice** (button **Open**). Step 1: the invoice picture next to what was read from it;
   the same boxes are the correction form. Step 2: a table with the invoice, our order and the
   delivery side by side, the difference, what was found and the draft note. Step 3: "I checked
   this invoice". Model labels, status codes, cents and the raw model response are folded into
   "Technical details" at the bottom.

The words on the page and the statuses of the brief:

| On the page | Status |
|---|---|
| All good | `reconciled` |
| Does not match | `discrepant` |
| Sent twice | `duplicate` |
| Order not found | `unresolved` |
| Could not read | `failed` |

To see the correction flow: open **Invoice INV-6 from S1** (file `po-typo`). The picture says
`P0-4` (digit zero), the box "Order number" says `PO-4`. Type `P0-4` and press **Save and check
again**. The result becomes "Order not found" (`unresolved`), the overcharged total on the list
goes from $25.00 to $20.00, the first reading is kept, and the state is still there after the app
is restarted. "Settings" at the bottom of the list has live mode and "start over".

Change an input and rerun: edit or add an invoice record in `data/additions.json`, add it to
`data/documents.json`, then

```bash
.venv/Scripts/python scripts/render_invoices.py data/additions.json data/images
.venv/Scripts/python -m app.run --mode live
```

(In replay mode a changed image is reported as `failed` with "recorded for a different image or
prompt": a saved response is never reused for a different input.)

## Replay without an API key

Every successful model response is saved as it was returned in `replay/extract/<file_id>.json`
(model, time, prompt version, token counts, a hash of prompt + image, raw output text).
`--mode replay` reads those files instead of calling the model, so the whole flow and all tests
run without a key. `api-error` has no saved response on purpose: it is a simulated failure and
is labelled so. `replay/history/` keeps responses from prompt versions that were tried and dropped.

Draft notes are saved the same way in `replay/notes/<file_id>.<hash of the facts>.json`. The facts
are part of the file name, so `po-typo` has two saved notes: one for the extracted `PO-4` and one
for the corrected `P0-4`. A correction that produces facts with no saved note shows
"no saved response" in replay mode instead of an old or invented note; live mode drafts a new one.

## Architecture

```
invoice images ──> extract.py ──> Pydantic validation ──> store.py (SQLite: original extraction)
                   (model reads)   (text → integer cents)        │  + reviewer corrections
                                                                 ▼
reference data ──> reference.py ──────────────────────> reconcile.py (code only: match by
(POs, receipts)                                          supplier_id + po_id, amounts, duplicates)
                                                                 │
                                    notes.py <── verified facts ─┤──> insight.py (counts causes)
                                    (model drafts a note,        ▼
                                     code checks it)      ui.py review queue ──> correction ──> rerun
```

| Module | What it does |
|---|---|
| `app/llm.py` | The only provider call. Live (saves the response), replay (reads it, refuses a response recorded for another input), simulated failure. Never raises. |
| `app/extract.py` | Image → model → strict JSON → `InvoiceFields` in integer cents, or a readable error. |
| `app/reconcile.py` | Pure functions: matching, expected amount, quantity checks, duplicates, statuses, totals. No model, no I/O. |
| `app/notes.py` | Builds the verified facts for a document, asks the model for a 2–4 sentence draft, rejects a draft that contains an ID or number not in the facts. |
| `app/insight.py` | Counts documents per cause of finding and prints the most frequent one with a suggestion. No model. |
| `app/store.py` | SQLite: documents, original extractions, corrections (separate rows), results, notes, review state. |
| `app/run.py` | Batch command; `recompute` is reused by the review app after every correction. |
| `app/ui.py` | Streamlit review queue. Shows only what is stored and what `reconcile.py` calculated. |

## Model configuration

- Provider and model: OpenAI `gpt-5.4-mini-2026-03-17` (pinned snapshot), Responses API with image input.
- Temperature 0. Structured output: strict JSON schema (`app/extract.py`), then Pydantic validation.
- The model returns the seven fields as printed text or `null`. Numbers are converted in code.
- Prompt: `prompts/extract_invoice_v1.txt`. `extract_invoice_v2.txt` was tried and dropped (see `docs/DEVLOG.md`, day 2).
- Only `app/llm.py` talks to the provider. Settings are in `app/config.py`.
- Notes: `prompts/draft_note_v1.txt`, same model and temperature, JSON schema `{"note": string}`.
  The model sees only facts already verified in code and its text is checked against them.

## Data

- Seeds: `tasks/invoices/` from starter pack version `2026-10-02` (unchanged).
- Additions: four invoices and one unreadable document in `data/` (8 invoices in two layouts + 1
  invalid input). What each one is for and how it was rendered: `data/GENERATION.md`. No random seed is used.
- The batch, in received order: `data/documents.json`. The app reads only the images listed there.
- Expected results: `data/expected-results.json`, written by hand before the app was run on the new
  documents; `scripts/check_expected.py` re-checks its arithmetic without importing the app.
  The five reference cases are laid out for a hand check in `docs/reference-cases.md`.

## Assumptions and ambiguities

Cases the supplied rules do not settle, and the behaviour chosen (implemented in `app/reconcile.py`,
covered by `tests/test_reconcile.py`):

| # | Case | Chosen behaviour |
|---|---|---|
| 1 | Two invoices share `supplier_id` + `invoice_number`: which is the original? | The first one in received order (order of the input list) is the original; later copies are `duplicate`. |
| 2 | Billed quantity ≠ received (or ordered) quantity, but the amount difference is 0 | `discrepant` with a quantity finding and `difference_cents = 0`; it adds nothing to the recoverable total. |
| 3 | No receipt for the matched PO | Received quantity is 0 → quantity finding → `discrepant`. |
| 4 | Invoice SKU differs from the PO SKU | Treated as a conflicting reference → `unresolved`, no expected amount. |
| 5 | Invoice disagrees with itself (`quantity × unit price ≠ total`) | `unresolved` with a "check the extracted values" finding. Most likely an extraction error; a reviewer correction re-runs reconciliation. |
| 6 | Billed less than expected (negative difference) | `discrepant` (undercharge), never added to the recoverable total. |
| 7 | Supplier ID or invoice number missing | `unresolved`; a duplicate check is impossible without both. |
| 8 | Formatting of IDs (`po-2 ` vs `PO-2`) | IDs are compared ignoring case and surrounding spaces. |
| 9 | What counts as payable | `reconciled` and `discrepant` invoices. `duplicate`, `unresolved` and `failed` do not. |
| 10 | Rounding | None. Amounts are parsed with `Decimal`; fractions of a cent are rejected as invalid extraction. All arithmetic is integer cents. |

## Check results (minimum demonstration)

Expected values come from the hand-written answer key (`data/expected-results.json`, hand
calculation in `docs/reference-cases.md`). Observed values are from `python -m app.run --mode replay`
on the saved real model responses. Amounts are in cents.

| # | Check | Expected | Observed | Pass |
|---|---|---|---|---|
| 1 | Clean invoice (`clean`, INV-1) matches the intended PO and receipt; amounts agree | `reconciled`, PO-1 + RC-1, expected 10000, billed 10000, difference 0 | `reconciled`, PO-1 + RC-1, 10000 / 10000 / 0, no findings | yes |
| 2 | Wrong unit price (`wrong-price`, INV-2) gives the expected discrepancy, linked to invoice and agreed price | `discrepant`, PO-2 + RC-2, expected 5 × 2000 = 10000, billed 12000, difference 2000 | `discrepant`, PO-2 + RC-2, 10000 / 12000 / 2000, findings `unit_price_mismatch` and `amount_difference` naming INV-2 and the agreed price | yes |
| 3 | Duplicate (`duplicate`, second INV-1 from S1) is flagged and excluded from payable totals | `duplicate` of `clean`, no expected amount, not payable, not recoverable | `duplicate` of `clean`, no PO and no expected amount shown; payable invoices = 4 without it | yes |
| 4 | Missing PO reference (`missing-reference`, INV-3) stays unresolved; no invented match or expected amount | `unresolved`, no PO, no expected amount, although PO-1 and PO-2 have the same amount | `unresolved`, PO none, expected none, finding `missing_po_reference` | yes |
| 5 | Correcting an extracted field (`po-typo`: `po_id` PO-4 → printed P0-4) reruns reconciliation and persists after restart | before: `discrepant`, recoverable 2500, payable 4; after: `unresolved`, recoverable 2000, payable 3; same after reopening the database; original extraction still PO-4 | before 2500 / 4; after `unresolved`, 2000 / 3; the same after closing and reopening the SQLite file; original extraction PO-4 kept | yes |

The same checks run as tests: `test_replayed_batch_against_the_hand_written_answer_key`,
`test_reviewer_correction_reruns_and_survives_a_restart` (`tests/test_pipeline.py`),
`test_review_page_correction_flow` (through the review page, `tests/test_notes_ui.py`) and the
rule tests in `tests/test_reconcile.py`. 54 tests pass; none calls the model.

**Failed check that could not be fixed:** the first extraction of `po-typo` did not match the
answer key. The invoice prints `P0-4`; the model returns `PO-4`. Three attempts did not change it
(see Known limitations), so it is reported, and it is the case used for check 5.

## Time spent

| Date | Work | Time |
|---|---|---|
| 2026-11-09 | Project folder and `CLAUDE.md` drafted with Claude (separate session) | TODO |
| 2026-11-09 | Brief, environment, model probe, `reconcile.py` + tests (see `docs/DEVLOG.md`) | ~0.5 h |
| 2026-11-10 | Added data + answer key, extraction with replay, SQLite store, batch run, tests | ~0.5 h |
| 2026-11-10 | Draft notes with a code check, process insight, review app with correction flow, tests | ~0.5 h |
| 2026-11-10 | Review screen reworked into numbered cards, check results, `ai-workflow/`, walkthrough, fresh-clone run | ~0.5 h |

Total: TODO before sending - the rows above plus my own reading, hand checks and clicking through the app (limit: 8 hours)

## Known limitations

- **Look-alike characters are misread.** The invoice `po-typo` prints `P0-4` (digit zero); the model
  returns `PO-4`, with both prompt versions, with image detail `auto` and `high`, and with the larger
  `gpt-5.4`. The app then matches PO-4 without any warning. Only a reviewer comparing the image with
  the extracted fields catches it. Details: `docs/DEVLOG.md`, day 2.
- **The note check is a simple text check.** It rejects a draft with an ID or number that is not in
  the verified facts. It does not check the meaning of the sentences, so a note is always shown as
  a draft for the reviewer, never as a decision.
- **Replay covers only recorded inputs.** A correction other than the documented one (`po-typo` →
  `P0-4`) changes the facts, and in replay mode the note is then shown as "no saved response".
  Statuses and amounts are still recalculated, because they do not need the model.
- **The process insight is a count on nine documents.** It shows the most frequent cause in this
  batch, not a trend.
- **Temperature 0 is not fully repeatable.** Three live runs returned the same extracted fields, but
  a second live run worded all six draft notes differently. This is why every response is saved
  and why the note check runs on every response, not once.
- **One line per invoice.** Tax, partial billing, several lines, other currencies and PDF input are
  outside the supplied rules and are not handled.
- **No login and one local user.** The SQLite file is the only state; there is no audit of who
  made a correction, only what was changed and when.
- **Optional enhancements were not attempted** (PDF, export, note revisions).

## LLM usage

- **Development tool:** Claude Code (desktop app) generated the code, tests, added data and most of
  this documentation. I set the rules in `CLAUDE.md`, decided what to build and in what order, and
  checked the results (answer key by hand, the app in the browser).
- **Application model:** OpenAI `gpt-5.4-mini-2026-03-17`, used for two things only: reading the
  invoice image and drafting the note.
- **One representative instruction and one correction:** `ai-workflow/README.md`.
- **Where AI output was wrong and what caught it:** `docs/DEVLOG.md` (a missing test found by
  breaking the rules on purpose; the `P0-4` misread found by the answer key; a note checker that
  rejected correct notes, found by reading the batch output).
- Walkthrough of the approach and findings: `docs/WALKTHROUGH.md`.
