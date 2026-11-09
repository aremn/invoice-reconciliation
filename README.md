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

TODO: run the batch and the review app.

## Replay without an API key

TODO: how to run the whole flow from saved real model responses in `replay/`.

## Architecture

TODO: flow diagram (images → extraction → validation → matching → calculation → notes → review queue)
and a short description of each module.

## Model configuration

TODO: provider, model ID, temperature, structured-output mode, prompts location.

## Data

- Seeds: `tasks/invoices/` from starter pack version `2026-10-02` (unchanged).
- Additions: TODO (which invoices, why, how they were generated, random seed if any).
- Expected results: TODO (where they live and how they were computed independently of the app).

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

Total: TODO (limit: 8 hours)

## Known limitations

TODO

## LLM usage

TODO: see `ai-workflow/README.md` for tools, models, one workflow example and one correction.
