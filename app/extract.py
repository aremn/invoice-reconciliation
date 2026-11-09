"""Invoice image -> model -> JSON text -> validated InvoiceFields.

The model only copies what is printed (all values as text). Converting quantities and
amounts to numbers happens here, in code. Anything that cannot be validated becomes an
error text, never a guessed value.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from app import llm
from app.config import PROMPTS_DIR, REPLAY_DIR
from app.models import InvoiceFields
from app.money import parse_cents

PROMPT_VERSION = "extract_invoice_v1"
MODEL_FIELDS = ("invoice_number", "supplier_id", "po_id", "sku", "quantity", "unit_price", "total")

# What the model must return: every field present, each either text or null.
JSON_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": ["string", "null"]} for name in MODEL_FIELDS},
    "required": list(MODEL_FIELDS),
    "additionalProperties": False,
}


class RawExtraction(BaseModel):
    """The model's answer before any conversion: printed text or null."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None
    supplier_id: str | None
    po_id: str | None
    sku: str | None
    quantity: str | None
    unit_price: str | None
    total: str | None


class ExtractionError(ValueError):
    pass


@dataclass
class Extraction:
    file_id: str
    label: str  # live | replayed | simulated-failure
    fields: InvoiceFields | None  # None when extraction failed
    error: str | None
    raw_text: str | None  # the model output exactly as returned
    model: str
    prompt_version: str
    recorded_at: str | None


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def parse_output(text: str) -> InvoiceFields:
    """Validate the model's JSON text and convert it. Raises ExtractionError."""
    try:
        raw = RawExtraction.model_validate_json(text)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'output'}: {e['msg']}" for e in exc.errors())
        raise ExtractionError(f"model output does not match the schema ({details})") from None

    values = {name: _text(getattr(raw, name)) for name in MODEL_FIELDS}
    if all(value is None for value in values.values()):
        raise ExtractionError("the model could not read any invoice field (unreadable document)")

    quantity = values["quantity"]
    if quantity is not None and not quantity.isdigit():
        raise ExtractionError(f"quantity is not a whole number: {quantity!r}")
    amounts = {}
    for name in ("unit_price", "total"):
        try:
            amounts[name] = None if values[name] is None else parse_cents(values[name])
        except ValueError as exc:
            raise ExtractionError(f"{name}: {exc}") from None

    return InvoiceFields(
        invoice_number=values["invoice_number"],
        supplier_id=values["supplier_id"],
        po_id=values["po_id"],
        sku=values["sku"],
        quantity=None if quantity is None else int(quantity),
        unit_cents=amounts["unit_price"],
        total_cents=amounts["total"],
    )


def load_prompt() -> str:
    return (PROMPTS_DIR / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8")


def extract_invoice(
    file_id: str,
    image_path: Path,
    mode: str,
    simulate: str | None = None,
    replay_dir: Path = REPLAY_DIR,
) -> Extraction:
    """Extract one invoice. Never raises: failures are returned in `error`."""
    answer = llm.run_model(
        mode=mode,
        replay_path=replay_dir / "extract" / f"{file_id}.json",
        prompt_version=PROMPT_VERSION,
        prompt=load_prompt(),
        schema_name="invoice_extraction",
        json_schema=JSON_SCHEMA,
        image_path=image_path,
        simulate=simulate,
    )
    fields, error = None, answer.error
    if error is None:
        try:
            fields = parse_output(answer.output_text)
        except ExtractionError as exc:
            error = str(exc)
    return Extraction(
        file_id=file_id, label=answer.label, fields=fields, error=error, raw_text=answer.output_text,
        model=answer.model, prompt_version=answer.prompt_version, recorded_at=answer.recorded_at,
    )
