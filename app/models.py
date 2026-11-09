"""Data shapes shared by the app. Money is always integer USD cents."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PurchaseOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    po_id: str
    supplier_id: str
    sku: str
    quantity: int = Field(gt=0)
    unit_cents: int = Field(ge=0)


class Receipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    receipt_id: str
    po_id: str
    sku: str
    quantity: int = Field(ge=0)


class InvoiceFields(BaseModel):
    """The fields reconciliation needs from one invoice document.

    They come from model extraction or from a reviewer correction. Any field can be
    missing (None) when it is not printed or could not be read; reconciliation then
    leaves the invoice unresolved instead of guessing.
    """

    invoice_number: str | None = None
    supplier_id: str | None = None
    po_id: str | None = None
    sku: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    unit_cents: int | None = Field(default=None, ge=0)
    total_cents: int | None = Field(default=None, ge=0)
