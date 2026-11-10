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

## Day 3 — 2026-11-10: draft notes, process insight, review app

**Done**
- `app/notes.py` + `prompts/draft_note_v1.txt`: for every `discrepant`, `duplicate` and `unresolved`
  document the code builds a list of verified facts (status, source IDs, amounts, findings) and the
  model writes a 2–4 sentence draft from them. After the answer the code checks that every ID and
  number in the draft is also in the facts; otherwise the draft is rejected and the error is shown.
  7 real responses saved in `replay/notes/` (6 documents + `po-typo` after the correction).
- `app/insight.py`: counts documents per cause of finding, no model. On this batch: PO reference
  problems, 2 of 9 documents before the `po-typo` correction and 3 of 9 after it.
- `app/store.py`: tables for notes and review state (reviewed + comment).
- `app/ui.py`: Streamlit review queue — status filter, image beside original and current fields,
  correction form → recalculation, matched PO and receipt, calculation in cents, findings, draft
  note, corrections history, raw model response, review state.
- `tests/test_notes_ui.py`: note check, replayed notes, insight, and a page test that runs the
  batch, corrects `po-typo`, marks it reviewed and opens the page again on the same database.
  54 tests pass; none calls the model. The app was also opened once in a browser in replay mode.

**What did not work / fixes**
1. *My note check rejected two correct notes.* The first replay showed "NOTE FAILED" for
   `wrong-price` and `duplicate`: "values that are not in the verified facts: 2," and "1,". The
   model was right; the number pattern in `check_note` took the comma after a number as part of
   the number ("2," is not in the facts, "2" is). Fixed the pattern (a comma only counts between
   groups of three digits) and added tests for accepted and rejected notes. No model call was repeated.
2. *The page test failed with `StopIteration`.* The test patched `app.ui.DB_PATH`, which imports
   `app/ui.py` as a normal module and runs the whole page outside Streamlit. Removed that line; the
   test now sets only `INVOICE_DB` / `app.config.DB_PATH`.
3. *Streamlit warned that `use_container_width` is deprecated.* Replaced with `width="stretch"`.
4. *A second live batch run re-recorded `replay/extract/`.* The extracted fields are the same as
   in the first run; only time and response id changed. Committed as the current recordings.

**Decisions**
- The facts are part of a note's file name and are stored with the note. If the findings change
  after a correction, the old note is not shown: the app drafts a new one (live) or says there is
  no saved response (replay).
- An unresolved document's facts say "there is no expected amount" and name no purchase order, so
  the note cannot suggest a match.
- The insight text says it is a count on a small simulated batch and not proof of wrongdoing.

**Next:** check-results table, `ai-workflow/` records, walkthrough, README limitations and total
time, run from a fresh clone, secret scan.

## Day 4 — 2026-11-10: review screen, check results, AI setup records

**Done**
- `app/ui.py` reworked. The first version was one long page and was hard to follow. Now one
  document is shown as numbered cards in the order a reviewer works: 1. the invoice image,
  2. what the model read (the same fields are the correction form), 3. our purchase order and
  receipt, 4. the calculation in dollars and cents, findings and draft note, 5. review state.
  Each status has a one-line explanation. Widget keys and labels were kept, so the page test did
  not change and still passes.
- README: check-results table for the five minimum checks (expected from the hand-written key,
  observed from a replay run), limitations, LLM usage. `docs/WALKTHROUGH.md`.
- `ai-workflow/manifest.json` and `ai-workflow/README.md` filled in from the templates.
- Run from a fresh clone (see below).

**What did not work / fixes**
1. *Temperature 0 did not give the same notes twice.* A live run from the review app re-recorded
   `replay/`. `git diff replay/` showed the extracted fields unchanged (third identical run), but
   all six notes were worded differently. All six still pass the note check, and the new recordings
   are committed. The note for `po-typo` after the correction was not re-recorded, because that
   state only exists after a correction.
2. *Walking through the first screen showed the design problem, not a test.* All tests passed on
   the long page; it was simply hard to read. Tests check behaviour, not whether a person can follow it.

**Fresh clone check.** Cloned the repository into an empty folder with no `.env`, created a new
venv, installed `requirements.txt`: 54 tests pass, `python -m app.run --mode replay` prints the same
table and totals (recoverable $25.00, 4 payable), all notes are accepted, `scripts/check_expected.py` is OK.

**Left for me before sending:** hand-check the five cases in `docs/reference-cases.md`, click
through the app, fill the total time in the README.

**Later the same day: plain words on the review page.** The people who review invoices are not
programmers, and the page still spoke in codes (`discrepant`, `unit_price_mismatch`, cents, model
and prompt names). Changed the wording only, no logic: each status has a plain name with the code
in brackets ("No order found (unresolved)"), one sentence under the invoice name says what is wrong
("The invoice is $20.00 higher than we agreed."), amounts are in dollars, our records have readable
column names, buttons say what they do ("Check all invoices", "Save and check again"), and model
labels, cents, finding codes and the raw response moved into one "Technical details" section.
Seen in the browser at a narrow width: seven numbers in one row were cut to "Matc...", "Over...";
the row now wraps. The page test was updated to the new labels and passes (54 tests).
