"""Load the local reference tables (purchase orders and receipts)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.models import PurchaseOrder, Receipt

DATA_DIR = Path(__file__).resolve().parent.parent / "tasks" / "invoices"


@dataclass(frozen=True)
class ReferenceData:
    purchase_orders: tuple[PurchaseOrder, ...]
    receipts: tuple[Receipt, ...]


def load_reference(path: Path = DATA_DIR / "seed.json") -> ReferenceData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pos = tuple(PurchaseOrder(**row) for row in raw["purchase_orders"])
    receipts = tuple(Receipt(**row) for row in raw["receipts"])

    po_ids = [po.po_id for po in pos]
    if len(po_ids) != len(set(po_ids)):
        raise ValueError(f"duplicate po_id in {path}")
    unknown = {r.po_id for r in receipts} - set(po_ids)
    if unknown:
        raise ValueError(f"receipts reference unknown purchase orders: {sorted(unknown)}")
    return ReferenceData(purchase_orders=pos, receipts=receipts)
