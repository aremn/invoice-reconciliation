# How the added data was made

The starter seeds in `tasks/invoices/` are unchanged (4 invoices, PO-1, PO-2, RC-1, RC-2).
Everything added for this submission is in this folder.

## Method

1. The added purchase orders, receipts and invoice records were written by hand (with Claude Code,
   following the project skill `.claude/skills/generate-assignment-data/SKILL.md`) into
   `data/additions.json`. It has the same structure as `tasks/invoices/seed.json`, and each invoice
   record follows `tasks/invoices/invoice.template.json`.
2. Images were rendered with `scripts/render_invoices.py`, a copy of the starter render script
   that takes the input file and output folder as arguments:

   ```bash
   .venv/Scripts/python scripts/render_invoices.py data/additions.json data/images
   ```

3. No random generation is used, so there is no random seed. Running the command again gives the
   same images.
4. The one optional extra field is `blur_radius` (only on `unreadable`): the finished image is
   blurred with `GaussianBlur(14)` to make a document nobody can read.

The seed images were not re-rendered. Re-rendering them with the installed Pillow 13.0.0 gives the
same layout and text but slightly different anti-aliasing (maximum pixel difference 28 of 255), so
the supplied PNG files are used as they are.

## What was added and why

| file_id | Layout | What is printed | Why it is here |
|---|---|---|---|
| `short-receipt` | a | INV-4, S1, PO-3, HUB-1, 5 × 35.00 = 175.00 | PO-3 ordered 5, receipt RC-3 confirms only 4: quantity check against the receipt |
| `supplier-conflict` | b | INV-5, S2, PO-1, CAB-1, 5 × 20.00 = 100.00 | PO-1 belongs to S1: a conflicting reference must stay unresolved |
| `po-typo` | a | INV-6, S1, **P0-4** (digit zero), ADP-1, 10 × 13.00 = 130.00 | Extraction-correction case: the reference does not match until a reviewer corrects it to PO-4 |
| `api-error` | b | INV-7, S2, PO-5, SW-1, 2 × 45.00 = 90.00 | The model call for this document is **simulated to fail** (see `data/documents.json`) |
| `unreadable` | a (blurred) | nothing legible | Deliberately invalid input: real model call on an unreadable image |

Reference rows added: PO-3 (S1, HUB-1, 5 × 3500), PO-4 (S1, ADP-1, 10 × 1250), PO-5 (S2, SW-1, 2 × 4500),
RC-3 (PO-3, 4 received), RC-4 (PO-4, 10), RC-5 (PO-5, 2).

Total: 8 invoices in two layouts plus one unreadable document. `api-error` and `unreadable` are
deliberate failure cases, not accidental data errors.

## The batch

`data/documents.json` lists the documents in received order with their image paths. The application
reads only these images. The invoice records in `seed.json` and `additions.json` are used for
rendering and for checking, never as application input.

## Expected results

`data/expected-results.json` was written by hand from the tables and `tasks/invoices/domain.md`,
before the application was run on the new documents. Each row names the rule and shows the
arithmetic. It also records what the recalculation must give after the reviewer corrects `po-typo`.

`scripts/check_expected.py` re-checks that file's arithmetic and ID links. It imports nothing from
`app/`, and it also confirms the supplied `expected-seed-results.json` still holds for the seed rows.

```bash
.venv/Scripts/python scripts/check_expected.py
```

The added rows change the totals: the supplied seed expectations cover four invoices; the totals
for the whole batch are in the `summary` block of `data/expected-results.json`.

## Open questions

The rule gaps found while writing these cases are listed in `README.md` → "Assumptions and ambiguities"
(for example: a quantity difference with a zero amount difference, and which copy of a duplicate is
the original). These fixtures say nothing about real-world model accuracy.
