"""Draft discrepancy notes.

The model gets only facts that the code has already verified (status, findings, source IDs,
amounts) and writes a short note from them. It decides nothing. After it answers, the code
checks that every ID and number in the note is also in the facts; a note that brings in
anything new is rejected and shown as an error instead.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app import llm
from app.config import PROMPTS_DIR, REPLAY_DIR
from app.models import InvoiceFields
from app.money import format_cents
from app.reconcile import ReconResult, Status

PROMPT_VERSION = "draft_note_v1"
NOTE_STATUSES = (Status.DISCREPANT, Status.DUPLICATE, Status.UNRESOLVED)  # nothing to explain otherwise
NOTE_SCHEMA = {
    "type": "object",
    "properties": {"note": {"type": "string"}},
    "required": ["note"],
    "additionalProperties": False,
}

ID_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")  # PO-2, RC-1, INV-6, CAB-1, P0-4
NUMBER_PATTERN = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")  # 5, 120.00, 1,200.50


@dataclass
class Note:
    file_id: str
    facts_hash: str  # which facts the note was written from
    label: str  # live | replayed | simulated-failure
    text: str | None
    error: str | None
    model: str
    recorded_at: str | None


def build_facts(result: ReconResult, fields: InvoiceFields) -> str:
    """The verified facts for one document, as plain lines of text."""
    lines = [
        f"Document: {result.file_id}",
        f"Invoice number: {fields.invoice_number or 'not readable'}; supplier: {fields.supplier_id or 'not readable'}",
        f"Purchase-order reference on the invoice: {fields.po_id or 'none'}",
        f"Status: {result.status.value}",
    ]
    if result.duplicate_of is not None:
        lines.append(f"Duplicate of the document: {result.duplicate_of}")
    if result.po_id is not None:
        lines.append(f"Matched purchase order: {result.po_id}")
    if result.expected_cents is not None:
        lines.append(f"Ordered: {result.ordered_qty} x {format_cents(result.agreed_unit_cents)} "
                     f"= {format_cents(result.expected_cents)} expected")
        lines.append(f"Receipts: {', '.join(result.receipt_ids) or 'none'}; received quantity: {result.received_qty}")
        lines.append(f"Billed: {fields.quantity} x {format_cents(fields.unit_cents)} = {format_cents(result.billed_cents)}")
        lines.append(f"Difference (billed - expected): {format_cents(result.difference_cents)}")
    else:
        lines.append("No purchase order is matched, so there is no expected amount.")
    lines.append("Verified findings:")
    lines += [f"- {finding.message}" for finding in result.findings]
    return "\n".join(lines)


def build_prompt(result: ReconResult, fields: InvoiceFields) -> str:
    template = (PROMPTS_DIR / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
    return template.replace("{facts}", build_facts(result, fields))


def facts_hash(result: ReconResult, fields: InvoiceFields) -> str:
    return llm.input_hash(build_prompt(result, fields), None)[:12]


def check_note(note: str, facts: str) -> str | None:
    """Return a problem text if the note has an ID or a number that is not in the facts."""
    if not note.strip():
        return "the note is empty"
    new_ids = set(ID_PATTERN.findall(note)) - set(ID_PATTERN.findall(facts))
    new_numbers = set(NUMBER_PATTERN.findall(note)) - set(NUMBER_PATTERN.findall(facts))
    extra = sorted(new_ids | {n for n in new_numbers if not any(n in i for i in new_ids)})
    if extra:
        return "the note mentions values that are not in the verified facts: " + ", ".join(extra)
    return None


def draft_note(result: ReconResult, fields: InvoiceFields, mode: str, replay_dir: Path = REPLAY_DIR) -> Note:
    """Draft one note. Never raises: a failed or rejected draft comes back with `error` set."""
    prompt = build_prompt(result, fields)
    key = llm.input_hash(prompt, None)[:12]
    answer = llm.run_model(
        mode=mode,
        # The facts are part of the file name, so the note for a corrected invoice is saved next to the old one.
        replay_path=replay_dir / "notes" / f"{result.file_id}.{key}.json",
        prompt_version=PROMPT_VERSION,
        prompt=prompt,
        schema_name="discrepancy_note",
        json_schema=NOTE_SCHEMA,
    )
    text, error = None, answer.error
    if error is None:
        try:
            text = json.loads(answer.output_text)["note"]
            error = check_note(text, build_facts(result, fields))
        except (ValueError, KeyError, TypeError):
            error = "model output is not the expected JSON with a 'note' text"
        if error is not None:
            text = None
    return Note(file_id=result.file_id, facts_hash=key, label=answer.label, text=text, error=error,
                model=answer.model, recorded_at=answer.recorded_at)


def draft_notes(store, results: list[ReconResult], mode: str, replay_dir: Path = REPLAY_DIR,
                only_changed: bool = False) -> None:
    """Draft and save a note for every document that needs one.

    With `only_changed` (used after a reviewer correction) a document keeps its note when
    its facts are the same as before, so no model call is repeated for it.
    """
    for result in results:
        fields = store.effective_fields(result.file_id)
        if result.status not in NOTE_STATUSES or fields is None:
            store.delete_note(result.file_id)
            continue
        old = store.note(result.file_id)
        if only_changed and old is not None and old.error is None and old.facts_hash == facts_hash(result, fields):
            continue
        store.save_note(draft_note(result, fields, mode, replay_dir))
