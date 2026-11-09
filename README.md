# Invoice Reconciliation & Review

Take-home assignment B: a small local platform that reads supplier invoices, matches them to
purchase orders and receipts, checks the amounts in code, and gives a reviewer a queue to
inspect, correct and re-run.

> Status: work in progress.

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

TODO: the review app.

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

## Architecture

TODO: flow diagram (images → extraction → validation → matching → calculation → notes → review queue)
and a short description of each module.

## Model configuration

- Provider and model: OpenAI `gpt-5.4-mini-2026-03-17` (pinned snapshot), Responses API with image input.
- Temperature 0. Structured output: strict JSON schema (`app/extract.py`), then Pydantic validation.
- The model returns the seven fields as printed text or `null`. Numbers are converted in code.
- Prompt: `prompts/extract_invoice_v1.txt`. `extract_invoice_v2.txt` was tried and dropped (see `docs/DEVLOG.md`, day 2).
- Only `app/llm.py` talks to the provider. Settings are in `app/config.py`.

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

| # | Check | Expected | Observed | Pass |
|---|---|---|---|---|
| 1 | Clean invoice matches the intended PO and receipt; amounts agree | | | |
| 2 | Wrong unit price gives the expected discrepancy, linked to invoice and agreed price | | | |
| 3 | Duplicate is flagged and excluded from payable totals | | | |
| 4 | Missing PO reference stays unresolved; no invented match or expected amount | | | |
| 5 | Correcting an extracted field reruns reconciliation and persists after restart | | | |

## Time spent

| Date | Work | Time |
|---|---|---|
| 2026-11-09 | Project folder and `CLAUDE.md` drafted with Claude (separate session) | TODO |
| 2026-11-09 | Brief, environment, model probe, `reconcile.py` + tests (see `docs/DEVLOG.md`) | ~0.5 h |
| 2026-11-10 | Added data + answer key, extraction with replay, SQLite store, batch run, tests | ~0.5 h |

Total: TODO (limit: 8 hours)

## Known limitations

- **Look-alike characters are misread.** The invoice `po-typo` prints `P0-4` (digit zero); the model
  returns `PO-4`, with both prompt versions, with image detail `auto` and `high`, and with the larger
  `gpt-5.4`. The app then matches PO-4 without any warning. Only a reviewer comparing the image with
  the extracted fields catches it. Details: `docs/DEVLOG.md`, day 2.
- TODO (rest)

## LLM usage

TODO: see `ai-workflow/README.md` for tools, models, one workflow example and one correction.
