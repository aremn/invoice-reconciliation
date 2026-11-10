"""Review queue (Streamlit).

Run:  streamlit run app/ui.py

The page only shows what is saved in SQLite and what app/reconcile.py calculated. A reviewer
correction is saved, everything is recalculated, and the page is drawn again.

The page reads top to bottom like the reviewer's work:
  batch summary -> queue -> one document:
  1. the invoice image   2. what the model read (and the correction form)
  3. our own records     4. the calculation, the findings and the draft note
  then the review state and the history.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "app" imports work under streamlit

import streamlit as st

from app.config import DB_PATH, ROOT
from app.insight import build_insight
from app.money import format_cents, parse_cents
from app.notes import draft_notes, facts_hash
from app.reconcile import Status, summarize
from app.reference import load_reference
from app.run import recompute, run_batch
from app.store import FIELD_NAMES, Store

LABELS = {
    "invoice_number": "Invoice number", "supplier_id": "Supplier ID", "po_id": "Purchase order",
    "sku": "SKU", "quantity": "Quantity", "unit_cents": "Unit price (USD)", "total_cents": "Total (USD)",
}
MONEY_FIELDS = ("unit_cents", "total_cents")

# What each status means for the reviewer, in one line, and the colour of its badge.
STATUS_HELP = {
    "reconciled": ("green", "The invoice agrees with the purchase order and the receipt."),
    "discrepant": ("orange", "A purchase order is matched, but the price or the quantity differs."),
    "duplicate": ("violet", "The same supplier already sent this invoice number. Not payable again."),
    "unresolved": ("blue", "No purchase order can be matched, so there is nothing to compare with."),
    "failed": ("red", "The document could not be read. See the error below."),
}


def to_text(name: str, value) -> str:
    """A stored field value as the text shown in the form (cents 2400 -> '24.00')."""
    if value is None:
        return ""
    if name in MONEY_FIELDS:
        return f"{value // 100}.{value % 100:02d}"
    return str(value)


def from_text(name: str, text: str):
    """Form text back to a field value. Empty means 'not on the invoice'. Raises ValueError."""
    text = text.strip()
    if not text:
        return None
    if name in MONEY_FIELDS:
        return parse_cents(text)
    if name == "quantity":
        if not text.isdigit():
            raise ValueError(f"quantity is not a whole number: {text!r}")
        return int(text)
    return text


def money(cents: int | None) -> str:
    return "-" if cents is None else format_cents(cents)


st.set_page_config(page_title="Invoice review queue", layout="wide")
store = Store(DB_PATH)
reference = load_reference()

# --- sidebar: run the batch ---------------------------------------------------------
with st.sidebar:
    st.header("Batch")
    mode = st.radio("Model calls", ["replay", "live"],
                    help="replay: saved real responses, no key. live: new calls, needs OPENAI_API_KEY.")
    if st.button("Run batch"):
        run_batch(mode, store)
    if st.button("Reset: forget corrections and reviews"):
        store.reset()
        run_batch(mode, store)
    st.caption("The model reads the invoice image and drafts the note. "
               "Matching, amounts and statuses are calculated in code.")

results = store.results()
if not results:
    st.info("No results yet. Press **Run batch** in the sidebar.")
    st.stop()

# --- batch summary ------------------------------------------------------------------
st.title("Invoice review queue")
summary = summarize(results)
columns = st.columns(len(summary.counts) + 2)
for column, (name, count) in zip(columns, summary.counts.items()):
    column.metric(name, count)
columns[-2].metric("recoverable overcharges", format_cents(summary.recoverable_cents))
columns[-1].metric("payable invoices", summary.payable_invoices)

insight = build_insight(results)
if insight is not None:
    st.caption("Process insight (counted in code): " + insight.text)

# --- queue with status filter -------------------------------------------------------
st.subheader("Queue")
chosen = st.multiselect("Show statuses", [s.value for s in Status], default=[s.value for s in Status])
visible = [r for r in results if r.status.value in chosen]
st.dataframe(
    [{
        "document": r.file_id,
        "status": r.status.value,
        "model answer": store.extraction(r.file_id).label,
        "PO": r.po_id or "-",
        "expected": money(r.expected_cents),
        "billed": money(r.billed_cents),
        "difference": money(r.difference_cents),
        "corrected": "yes" if store.corrections(r.file_id) else "",
        "reviewed": "yes" if store.review(r.file_id)[0] else "",
    } for r in visible],
    hide_index=True, width="stretch",
)
if not visible:
    st.stop()

# --- one document -------------------------------------------------------------------
file_id = st.selectbox("Document", [r.file_id for r in visible])
result = next(r for r in visible if r.file_id == file_id)
extraction = store.extraction(file_id)
current = store.effective_fields(file_id)
document = next(d for d in store.documents() if d["file_id"] == file_id)
corrections = store.corrections(file_id)

colour, meaning = STATUS_HELP[result.status.value]
st.subheader(file_id)
st.badge(result.status.value, color=colour)
st.write(meaning)

left, right = st.columns(2)

# 1. the invoice as it arrived
with left.container(border=True):
    st.markdown("**1. The invoice**")
    image_path = ROOT / document["image"]
    if image_path.exists():
        st.image(str(image_path), caption=document["image"])
    else:
        st.error(f"Image not found: {document['image']}")

# 2. what the model read from it, and the correction form
with right.container(border=True):
    st.markdown("**2. What the model read** - compare with the image")
    st.caption(f"`{extraction.label}` answer, model `{extraction.model}`, prompt `{extraction.prompt_version}`")
    if extraction.error:
        st.error(f"Extraction failed: {extraction.error}")
    with st.form(f"correct-{file_id}"):
        typed = {
            name: st.text_input(LABELS[name], value=to_text(name, getattr(current, name)) if current else "",
                                key=f"{file_id}-{name}")
            for name in FIELD_NAMES
        }
        st.caption("If a value differs from the image, type what is printed. Empty = not on the invoice.")
        if st.form_submit_button("Save correction and rerun"):
            try:
                new_values = {name: from_text(name, text) for name, text in typed.items()}
                changed = {name: value for name, value in new_values.items()
                           if value != (getattr(current, name) if current else None)}
                for name, value in changed.items():
                    store.add_correction(file_id, name, value)
            except ValueError as exc:
                st.error(f"Not saved: {exc}")
            else:
                if changed:
                    draft_notes(store, recompute(store, reference), mode, only_changed=True)
                    st.rerun()
                st.info("Nothing was changed.")
    if corrections:
        st.markdown("Corrected by the reviewer (the model's original answer is kept):")
        st.table([{
            "field": LABELS[c["field"]],
            "model read": to_text(c["field"], json.loads(c["old_value"])),
            "corrected to": to_text(c["field"], json.loads(c["new_value"])),
            "when (UTC)": c["corrected_at"],
        } for c in corrections])

left, right = st.columns(2)

# 3. our own records for this invoice
with left.container(border=True):
    st.markdown("**3. Our records**")
    if result.po_id is None:
        st.write("No purchase order is matched, so no expected amount is shown.")
    else:
        st.caption("Purchase order (what was agreed)")
        st.table([po.model_dump() for po in reference.purchase_orders if po.po_id == result.po_id])
        st.caption("Receipt (what was delivered)")
        st.table([r.model_dump() for r in reference.receipts if r.receipt_id in result.receipt_ids]
                 or [{"receipt": "no receipt recorded"}])

# 4. the comparison, done in code
with right.container(border=True):
    st.markdown("**4. Check** - calculated in code, not by the model")
    if result.expected_cents is not None:
        st.table([
            {"": "Expected", "calculation": f"ordered {result.ordered_qty} x agreed {money(result.agreed_unit_cents)}",
             "amount": money(result.expected_cents)},
            {"": "Billed", "calculation": "total on the invoice", "amount": money(result.billed_cents)},
            {"": "Difference", "calculation": "billed - expected", "amount": money(result.difference_cents)},
        ])
        st.caption(f"In cents: {result.billed_cents} - {result.expected_cents} = {result.difference_cents}. "
                   f"Received quantity: {result.received_qty}.")
    st.markdown("Findings")
    for finding in result.findings:
        st.write(f"- `{finding.code}` {finding.message}")
    if not result.findings:
        st.write("None.")

    note = store.note(file_id)
    if note is not None:
        st.markdown(f"Draft note - written by the model from the findings above (`{note.label}`). A draft, not a decision.")
        if note.error:
            st.warning(f"No note: {note.error}")
        elif current is not None and note.facts_hash != facts_hash(result, current):
            st.warning("The findings changed after this note was written. Run the batch to draft a new one.")
        else:
            st.info(note.text)

# --- review state -------------------------------------------------------------------
reviewed, comment = store.review(file_id)
with st.form(f"review-{file_id}"):
    st.markdown("**5. Review state**")
    new_reviewed = st.checkbox("Reviewed", value=reviewed, key=f"{file_id}-reviewed")
    new_comment = st.text_input("Reviewer comment", value=comment, key=f"{file_id}-comment")
    if st.form_submit_button("Save review state"):
        store.save_review(file_id, new_reviewed, new_comment)
        st.rerun()

# --- raw model output, for inspecting a failure --------------------------------------
with st.expander("Raw model response"):
    st.write(f"label: `{extraction.label}` - recorded: {extraction.recorded_at or '-'}")
    if extraction.fields is not None:
        st.write("Original extraction: " + ", ".join(
            f"{LABELS[name]} = {to_text(name, getattr(extraction.fields, name)) or '(none)'}" for name in FIELD_NAMES))
    st.code(extraction.raw_text or "(no response)", language="json")

store.close()
