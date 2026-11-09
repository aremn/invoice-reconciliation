# Invoice Reconciliation & Review

Take-home assignment B: a small local platform that reads supplier invoices, matches them to
purchase orders and receipts, checks the amounts in code, and gives a reviewer a queue to
inspect, correct and re-run.

> Status: work in progress.

## Setup

TODO: Python version, install command, environment variables (`.env.example`).

## Run

TODO: run the app, run the batch, run the tests.

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

TODO: every case the rules do not cover and the behaviour chosen. Candidates noticed so far:

- Which of two invoices with the same `supplier_id` + `invoice_number` is the original and which is the duplicate.
- Billed quantity equals ordered quantity, but fewer items were received: the amount difference is 0,
  yet quantities disagree. Which status should this get?

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

Total: TODO (limit: 8 hours)

## Known limitations

TODO

## LLM usage

TODO: see `ai-workflow/README.md` for tools, models, one workflow example and one correction.
