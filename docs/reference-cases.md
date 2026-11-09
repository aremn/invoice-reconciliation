# Five reference cases

These five cases cover the brief's minimum demonstration. Each one can be checked with the invoice
image, the two reference tables and a calculator; the application is not needed.
Source tables: `tasks/invoices/seed.json` (PO-1, PO-2, RC-1, RC-2) and `data/additions.json` (PO-3 to PO-5, RC-3 to RC-5).
Rules: `tasks/invoices/domain.md`. All amounts are USD cents.

The machine-readable answer key is `data/expected-results.json`; the app's observed results are
compared with it in `docs/check-results.md` (added with the final checks).

## 1. Clean invoice — `tasks/invoices/images/clean.png`

| Source | Record |
|---|---|
| Invoice | INV-1, supplier S1, PO-1, CAB-1, quantity 5, unit 20.00, total 100.00 |
| Purchase order | PO-1: S1, CAB-1, quantity 5, unit 2000 |
| Receipt | RC-1: PO-1, quantity 5 |

- Match: S1 + PO-1 → PO-1 (same supplier).
- Expected = 5 × 2000 = **10000**. Billed = **10000**. Difference = 10000 − 10000 = **0**.
- Quantities: billed 5 = ordered 5 = received 5.
- Expected status: **reconciled**.

## 2. Wrong unit price — `tasks/invoices/images/wrong-price.png`

| Source | Record |
|---|---|
| Invoice | INV-2, supplier S1, PO-2, CAB-1, quantity 5, unit 24.00, total 120.00 |
| Purchase order | PO-2: S1, CAB-1, quantity 5, unit 2000 |
| Receipt | RC-2: PO-2, quantity 5 |

- Expected = 5 × 2000 = **10000**. Billed = 5 × 2400 = **12000**. Difference = 12000 − 10000 = **+2000** (overcharge).
- Expected status: **discrepant**; the finding must name PO-2 and the agreed price 20.00.

## 3. Duplicate — `tasks/invoices/images/duplicate.png`

| Source | Record |
|---|---|
| Invoice | INV-1, supplier S1 (the same supplier + invoice number as case 1) |

- `clean` is received first, so `duplicate` is the copy.
- Expected status: **duplicate**, not payable, no expected amount, nothing added to the recoverable total.
- Payable invoices in the whole batch: **3** (`clean`, `wrong-price`, `short-receipt`), not 4.

## 4. Missing purchase-order reference — `tasks/invoices/images/missing-reference.png`

| Source | Record |
|---|---|
| Invoice | INV-3, supplier S1, purchase order "(missing)", CAB-1, quantity 5, unit 20.00, total 100.00 |

- PO-1 and PO-2 both fit by supplier, SKU, quantity and amount, so the amount cannot decide.
- Expected status: **unresolved**; no matched PO, **no expected amount**, no difference.

## 5. Extraction correction — `data/images/po-typo.png`

| Source | Record |
|---|---|
| Invoice | INV-6, supplier S1, purchase order **P0-4** (digit zero), ADP-1, quantity 10, unit 13.00, total 130.00 |
| Purchase order | PO-4: S1, ADP-1, quantity 10, unit 1250 |
| Receipt | RC-4: PO-4, quantity 10 |

- Before correction: there is no purchase order "P0-4" → **unresolved**, no expected amount.
  The app must not pick PO-4 by itself.
- The reviewer corrects the extracted `po_id` to `PO-4` and reruns.
- After correction: expected = 10 × 1250 = **12500**. Billed = 10 × 1300 = **13000**.
  Difference = 13000 − 12500 = **+500** → **discrepant**.
- Recoverable total for the batch: **2000** before the correction, **2500** after it.
- The corrected value and the new result must still be there after the app is restarted, and the
  original extraction (`P0-4`) must stay visible.

## Hand check

| # | Case | Checked by hand by | Date | Agrees with `data/expected-results.json` |
|---|---|---|---|---|
| 1 | clean | | | |
| 2 | wrong-price | | | |
| 3 | duplicate | | | |
| 4 | missing-reference | | | |
| 5 | po-typo correction | | | |
