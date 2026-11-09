# Invoice Reconciliation & Review — project instructions

Take-home assignment B (Junior AI Engineer). A small local app that reads supplier
invoice images with a document-capable model, matches them to purchase orders and
receipts, checks amounts in code, and gives a reviewer a queue to inspect and correct.

- Full brief: `starter/brief-B.txt` (source HTML: `starter/assignment-brief.html`).
- Domain rules (source of truth): `tasks/invoices/domain.md`.
- Seeds and expected seed results: `tasks/invoices/seed.json`, `tasks/invoices/expected-seed-results.json`.
- Hard limit: 8 hours of work in total, including data preparation and documentation.
  Finish the required flow before anything optional. Document unfinished work instead of overrunning.

## Non-negotiable rules

1. **The model only reads and writes text.** It extracts fields from invoice images and drafts
   discrepancy notes from already-verified findings. Matching, amounts, statuses and totals are
   plain Python code, never model output.
2. **Money is integer USD cents.** No floats for money anywhere. Expected line amount =
   ordered quantity × agreed unit price. Discrepancy = billed − expected (positive = overcharge).
3. **Match only by `supplier_id` + `po_id`.** A missing or conflicting reference stays `unresolved`.
   Never pick the closest-looking record and never show an expected amount for an unresolved invoice.
4. **Duplicates** are identified by `supplier_id` + `invoice_number` and are never counted as payable.
   Duplicates and unresolved invoices are excluded from any recoverable total.
5. **Do not add domain rules.** If the rules do not cover a case, record the ambiguity in
   `README.md` ("Assumptions and ambiguities") and choose the simplest documented behaviour.
6. **Expected results are independent of the app.** Compute them by hand or a separate script.
   Never use the application's output as the answer key.
7. **Every real model response is saved** under `replay/` so the app runs without an API key.
   Label each result as `live`, `replayed` or `simulated-failure`.
8. **One bad invoice never stops the batch.** Unreadable images, invalid JSON, schema errors and
   API failures become a visible `failed` status with the error message.
9. **No secrets in the repo.** Keys come from environment variables (see `.env.example`).
   Never print, log or commit a key.

## Planned architecture

Python 3.11, Streamlit (review UI), SQLite (state), Pydantic (validation), pytest (checks).

| Module | Responsibility |
|---|---|
| `app/llm.py` | The only place that calls the model provider. Live mode and replay mode. |
| `app/extract.py` | Image → model → JSON → Pydantic `InvoiceExtraction`. Saves raw responses to `replay/`. |
| `app/reconcile.py` | Pure functions, no I/O, no model: match, expected amounts, quantity checks, duplicates, statuses. |
| `app/notes.py` | Model drafts a short discrepancy note from verified findings and source IDs only. |
| `app/store.py` | SQLite: original extraction, reviewer corrections, results, review state. Survives restart. |
| `app/ui.py` | Streamlit review queue with status filters, image beside extracted fields, correction → rerun. |
| `scripts/` | Data generation (reuse `tasks/invoices/render_invoices.py`) and expected-results calculation. |
| `tests/` | Five reference cases from the brief's "Minimum demonstration", plus unit tests for `reconcile.py`. |

Statuses: `reconciled`, `discrepant`, `duplicate`, `unresolved`, `failed`.

Model provider and model ID: decide at the start and record them in `ai-workflow/manifest.json`.
Use temperature 0 and a JSON / structured-output mode.

## How to work in this repo

- Plan first, then build in small steps. After each module: run the tests, then explain the module
  to Armen in plain words (what it does, why, one edge case). He must be able to explain every file
  at the follow-up interview, so prefer simple, readable code over clever code.
- Keep `reconcile.py` small and fully unit-tested. It is the part reviewers will probe.
- Run `pytest` before saying a step is done. Report failures honestly; do not weaken tests to pass.
- Commit in small steps with clear messages; history is part of the submission.
- Update `README.md` time log and `ai-workflow/` records as you go, not at the end.

## Commands

To be filled in once the project is set up (install, run app, run tests, replay without key).
