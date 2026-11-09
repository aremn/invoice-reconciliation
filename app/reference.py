"""Load the local reference tables (purchase orders and receipts)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import REFERENCE_FILES
from app.models import PurchaseOrder, Receipt


@dataclass(frozen=True)
class ReferenceData:
    purchase_orders: tuple[PurchaseOrder, ...]
    receipts: tuple[Receipt, ...]


def load_reference(paths: tuple[Path, ...] = REFERENCE_FILES) -> ReferenceData:
    """Read purchase orders and receipts from every file. Invoice records in them are ignored."""
    pos: tuple[PurchaseOrder, ...] = ()
    receipts: tuple[Receipt, ...] = ()
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        pos += tuple(PurchaseOrder(**row) for row in raw["purchase_orders"])
        receipts += tuple(Receipt(**row) for row in raw["receipts"])

    po_ids = [po.po_id for po in pos]
    if len(po_ids) != len(set(po_ids)):
        raise ValueError("duplicate po_id in the reference tables")
    unknown = {r.po_id for r in receipts} - set(po_ids)
    if unknown:
        raise ValueError(f"receipts reference unknown purchase orders: {sorted(unknown)}")
    return ReferenceData(purchase_orders=pos, receipts=receipts)
