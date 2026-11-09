# Development log

Short notes per working session: what was done, what did not work and why, and how it was fixed.
Development used Claude Code (see `ai-workflow/README.md`); the checks described here were run on real output.

## Day 1 — 2026-11-09: setup and reconciliation core

**Done**
- Read the brief (alternative B) and `tasks/invoices/domain.md`; checked that the copied seed files
  and images are byte-identical to the starter pack zip.
- Python 3.11 venv, `requirements.txt`, pytest config.
- Picked the application model (below).
- `app/models.py`, `app/reference.py`, `app/money.py`, `app/reconcile.py` + 30 unit tests.

**Model choice.** Sent the same invoice image (`wrong-price.png`) to three configurations through the
OpenAI Responses API and asked for invoice number, PO and total:

| Model | Setting | Answer | Input tokens | Time |
|---|---|---|---|---|
| gpt-5.4-mini-2026-03-17 | temperature 0 | `INV-2 PO-2 120.00` | 778 | 5.3 s |
| gpt-5.4-mini-2026-03-17 | reasoning effort low | `INV-2 PO-2 120.00` | 778 | 5.2 s |
| gpt-4.1-mini-2025-04-14 | temperature 0 | `INV-2, PO-2, 120.00` | 1044 | 2.0 s |

All three read the image correctly. Chose `gpt-5.4-mini-2026-03-17` with temperature 0: a pinned
snapshot (results stay reproducible), it accepts temperature 0, and the image costs fewer input
tokens. Speed does not matter for a batch of eight invoices.

**What did not work / fixes**
1. *Git warned about CRLF on every file* (Windows `core.autocrlf`). Added `.gitattributes` with
   `eol=lf` and renormalised, so the repo has the same line endings on any OS.
2. *The tests had a gap.* All 30 tests passed on the first run, so I broke the rules on purpose to
   see whether the tests notice:
   - expected amount from *billed* quantity instead of *ordered* quantity → caught;
   - supplier check removed → caught;
   - negative differences (undercharges) counted as recoverable → **not caught**, all tests passed.

   Added `test_undercharge_is_discrepant_but_not_recoverable`; the same mutation now fails it.

**Decisions** (also listed in README → Assumptions and ambiguities)
- An invoice whose `quantity × unit price ≠ total` is `unresolved`, not `discrepant`: the most likely
  cause is a misread field, and a reviewer correction should fix it rather than produce a false claim.
- No rounding: amounts are parsed with `Decimal` and fractions of a cent are rejected.

**Agent instructions changed.** Added a "Reviewability" section to `CLAUDE.md`, based on the
hiring-team part of the assignment page (summarised by a separate Claude session and checked against
the page text): plain code, inspectable failures, one-command rerun after changing an input, expected
results kept apart from app output, and a record of real AI mistakes caught by checks.

**Next (day 2):** extend the data to 6–8 invoices (incl. an extraction-correction case) with
independently computed expected results; model extraction with structured output; save real
responses for replay; batch run into SQLite.

## Day 2 — 2026-11-10

**Done**
- Data: four more invoices and one unreadable (blurred) document, three more purchase orders and
  receipts (`data/additions.json`, rendered with `scripts/render_invoices.py`). Batch order in
  `data/documents.json`. Method in `data/GENERATION.md`.
- Answer key `data/expected-results.json`, written by hand before the app saw the new documents,
  plus `scripts/check_expected.py` (imports nothing from `app/`). I changed one number in the key on
  purpose to see that the checker reports it; it did.
- `app/llm.py` (the only provider call, live / replay / simulated failure), `app/extract.py`
  (strict JSON schema → Pydantic → integer cents), `app/store.py` (SQLite: original extraction,
  corrections, results), `app/run.py` (batch command). 46 tests pass; none of them calls the model.
- One live run of the batch: 8 real calls (about 1,040 input and 50 output tokens each) + 1 simulated failure.

**What did not work / fixes**
1. *The model "fixed" a typo it was told to copy.* `po-typo` prints `P0-4` (digit zero). The model
   returned `PO-4`, so the app matched PO-4 and reported a $5.00 overcharge, while the answer key
   says `unresolved`. Caught by comparing the batch table with `data/expected-results.json`
   (7 of 8 real extractions matched, this one did not). Tried:
   - prompt v2 with an explicit line about digit 0 vs letter O → still `PO-4`;
   - image `detail: high` instead of `auto` → still `PO-4` (same token count);
   - the larger `gpt-5.4` → still `PO-4`.

   Nothing fixed it, so prompt v2 was dropped (v1 stays active; both files and both responses are
   kept in `prompts/` and `replay/history/`). No rule was added to the code to guess around it.
   It is recorded as a known limitation, and it became the extraction-correction case: the reviewer
   corrects the extracted `po_id` to the printed `P0-4`, the rerun gives `unresolved` and the
   recoverable total drops from $25.00 to $20.00 (`test_reviewer_correction_reruns_and_survives_a_restart`).
   The answer key was not edited: it already had both hand-calculated results (P0-4 and PO-4).
2. *Tests failed on this machine with `PermissionError` on the system temp folder.* pytest now uses a
   folder inside the project (`--basetemp=.pytest_tmp`, git-ignored).
3. *`from app.reference import DATA_DIR` broke* after the reference loader started reading two files;
   paths now live in `app/config.py`.

**Decisions**
- The model returns every field as printed text; quantities and amounts are converted in code, so a
  value like "five" or "20.005" becomes a visible `failed`, not a silently rounded number.
- All seven fields `null` = unreadable document = `failed`.
- Each saved response stores a hash of prompt + image, and replay refuses a response recorded for a
  different input, so an old answer is never shown for a changed invoice.
- A new batch run keeps reviewer corrections; `--reset` or a changed image drops them.

**Next:** discrepancy notes drafted by the model from verified findings, the Streamlit review queue
with the correction flow, the process-improvement insight, check results, `ai-workflow/` records.
