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
