"""Review queue (Streamlit).

Run:  streamlit run app/ui.py

The page is written for a reviewer who is not a programmer. It only shows what is saved in
SQLite and what app/reconcile.py calculated. A reviewer correction is saved, everything is
recalculated, and the page is drawn again.

The page reads top to bottom like the reviewer's work:
  summary -> list of invoices -> one invoice:
  1. the invoice picture     2. what was read from it (and the correction form)
  3. our own records         4. the check: amounts, what was found, draft note
  5. "I checked this"        and, folded away, the technical details.
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
from app.reconcile import ReconResult, Status, summarize
from app.reference import load_reference
from app.run import recompute, run_batch
from app.store import FIELD_NAMES, Store

LABELS = {
    "invoice_number": "Invoice number", "supplier_id": "Supplier", "po_id": "Order number (PO)",
    "sku": "Item code", "quantity": "Quantity", "unit_cents": "Price per unit, $", "total_cents": "Total, $",
}
MONEY_FIELDS = ("unit_cents", "total_cents")

# Plain name and badge colour for each status. The status code stays visible in brackets.
STATUS_NAMES = {
    "reconciled": ("Matches", "green"),
    "discrepant": ("Differs", "orange"),
    "duplicate": ("Duplicate", "violet"),
    "unresolved": ("No order found", "blue"),
    "failed": ("Could not read", "red"),
}
MODES = {"replay": "Use saved answers (no key needed)", "live": "Ask the model again (needs a key)"}


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


def status_label(status: str) -> str:
    name = STATUS_NAMES[status][0]
    return name if name.lower() == status else f"{name} ({status})"


def verdict(result: ReconResult) -> str:
    """One plain sentence about the result. Wording only: every fact comes from `result`."""
    if result.status is Status.RECONCILED:
        return "Everything on this invoice matches our order and the delivery."
    if result.status is Status.DUPLICATE:
        return f"We already have this invoice (see '{result.duplicate_of}'). It must not be paid twice."
    if result.status is Status.UNRESOLVED:
        return "We could not find the order this invoice belongs to, so there is nothing to compare it with."
    if result.status is Status.FAILED:
        return "This document could not be read. Nothing was checked."
    if result.difference_cents > 0:
        return f"The invoice is {format_cents(result.difference_cents)} higher than we agreed."
    if result.difference_cents < 0:
        return f"The invoice is {format_cents(-result.difference_cents)} lower than we agreed."
    return "The amount is right, but the quantity does not match our records."


st.set_page_config(page_title="Invoice review", layout="wide")
store = Store(DB_PATH)
reference = load_reference()

# --- sidebar: check the invoices ----------------------------------------------------
with st.sidebar:
    st.header("Start here")
    mode = st.radio("How to read the invoices", list(MODES), format_func=MODES.get)
    if st.button("Check all invoices", type="primary"):
        run_batch(mode, store)
    if st.button("Start over (forget my corrections)"):
        store.reset()
        run_batch(mode, store)
    st.caption("A model reads each invoice picture. The comparison with our orders and all "
               "amounts are calculated by the program, not by the model.")

results = store.results()
if not results:
    st.info("No results yet. Press **Check all invoices** on the left.")
    st.stop()

# --- summary ------------------------------------------------------------------------
st.title("Invoice review")
with st.expander("How to use this page"):
    st.markdown(
        "1. Pick an invoice from the list.\n"
        "2. Compare the picture (card 1) with what was read from it (card 2).\n"
        "3. If a value was read wrongly, type the right one and press **Save and check again**.\n"
        "4. Look at the result in card 4, then tick **I checked this invoice**."
    )
summary = summarize(results)
with st.container(horizontal=True):  # a row that wraps on a narrow screen instead of cutting the labels
    for name, count in summary.counts.items():
        st.metric(STATUS_NAMES[name][0], count, border=True, width="content")
with st.container(horizontal=True):
    st.metric("Overcharged in total", format_cents(summary.recoverable_cents), border=True, width="content",
              help="Sum of the overcharges on matched invoices. Duplicates and invoices without an order are not counted.")
    st.metric("Invoices that can be paid", summary.payable_invoices, border=True, width="content",
              help="Matched invoices. Duplicates, unread documents and invoices without an order are not counted.")

insight = build_insight(results)
if insight is not None:
    st.info("**What keeps going wrong:** " + insight.text)

# --- list of invoices ---------------------------------------------------------------
st.subheader("Invoices")
show = st.pills("Show", ["all"] + [s.value for s in Status], default="all",
                format_func=lambda value: "All invoices" if value == "all" else status_label(value))
visible = [r for r in results if show in ("all", None, r.status.value)]
st.dataframe(
    [{
        "invoice": r.file_id,
        "result": status_label(r.status.value),
        "we expected": money(r.expected_cents),
        "they billed": money(r.billed_cents),
        "difference": money(r.difference_cents),
        "corrected": "yes" if store.corrections(r.file_id) else "",
        "checked": "yes" if store.review(r.file_id)[0] else "",
    } for r in visible],
    hide_index=True, width="stretch",
)
if not visible:
    st.stop()

# --- one invoice --------------------------------------------------------------------
file_id = st.selectbox("Open an invoice", [r.file_id for r in visible])
result = next(r for r in visible if r.file_id == file_id)
extraction = store.extraction(file_id)
current = store.effective_fields(file_id)
document = next(d for d in store.documents() if d["file_id"] == file_id)
corrections = store.corrections(file_id)

st.subheader(file_id)
st.badge(status_label(result.status.value), color=STATUS_NAMES[result.status.value][1])
st.markdown(f"#### {verdict(result)}")

left, right = st.columns(2)

# 1. the invoice as it arrived
with left.container(border=True):
    st.markdown("**1. The invoice we received**")
    image_path = ROOT / document["image"]
    if image_path.exists():
        st.image(str(image_path))
    else:
        st.error(f"Picture not found: {document['image']}")

# 2. what the model read from it, and the correction form
with right.container(border=True):
    st.markdown("**2. What was read from it** - please compare with the picture")
    if extraction.error:
        st.error(f"The document could not be read: {extraction.error}")
    with st.form(f"correct-{file_id}"):
        typed = {
            name: st.text_input(LABELS[name], value=to_text(name, getattr(current, name)) if current else "",
                                key=f"{file_id}-{name}")
            for name in FIELD_NAMES
        }
        st.caption("Something is different from the picture? Type what is printed there. "
                   "Leave a box empty if the invoice does not show it.")
        if st.form_submit_button("Save and check again"):
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
        st.markdown("Your corrections (the first reading is kept):")
        st.table([{
            "what": LABELS[c["field"]],
            "was read as": to_text(c["field"], json.loads(c["old_value"])),
            "you corrected to": to_text(c["field"], json.loads(c["new_value"])),
            "when (UTC)": c["corrected_at"],
        } for c in corrections])

left, right = st.columns(2)

# 3. our own records for this invoice
with left.container(border=True):
    st.markdown("**3. What our records say**")
    if result.po_id is None:
        st.write("No order was found for this invoice, so there is no expected amount.")
    else:
        st.caption("Our order - what we agreed to buy")
        st.table([{"order": po.po_id, "supplier": po.supplier_id, "item": po.sku, "quantity": po.quantity,
                   "price per unit": money(po.unit_cents)}
                  for po in reference.purchase_orders if po.po_id == result.po_id])
        st.caption("Delivery - what actually arrived")
        st.table([{"receipt": r.receipt_id, "order": r.po_id, "item": r.sku, "quantity": r.quantity}
                  for r in reference.receipts if r.receipt_id in result.receipt_ids]
                 or [{"receipt": "nothing was recorded as delivered"}])

# 4. the comparison, done in code
with right.container(border=True):
    st.markdown("**4. The check**")
    if result.expected_cents is not None:
        st.table([
            {"": "We expected", "how": f"{result.ordered_qty} ordered x {money(result.agreed_unit_cents)} agreed",
             "amount": money(result.expected_cents)},
            {"": "They billed", "how": "total on the invoice", "amount": money(result.billed_cents)},
            {"": "Difference", "how": "billed minus expected", "amount": money(result.difference_cents)},
        ])
        st.write(f"Delivered: {result.received_qty}. Ordered: {result.ordered_qty}.")
    st.markdown("What was found:")
    for finding in result.findings:
        st.write(f"- {finding.message}")
    if not result.findings:
        st.write("Nothing. No problems.")

    note = store.note(file_id)
    if note is not None:
        st.markdown("Suggested note (a draft written by the model - read it before using it):")
        if note.error:
            st.warning(f"No note is available: {note.error}")
        elif current is not None and note.facts_hash != facts_hash(result, current):
            st.warning("The result changed after this note was written. Press **Check all invoices** to get a new one.")
        else:
            st.info(note.text)

# 5. review state
reviewed, comment = store.review(file_id)
with st.form(f"review-{file_id}"):
    st.markdown("**5. Done?**")
    new_reviewed = st.checkbox("I checked this invoice", value=reviewed, key=f"{file_id}-reviewed")
    new_comment = st.text_input("Comment (optional)", value=comment, key=f"{file_id}-comment")
    if st.form_submit_button("Save"):
        store.save_review(file_id, new_reviewed, new_comment)
        st.rerun()

# --- technical details, for inspecting a failure -------------------------------------
with st.expander("Technical details"):
    st.write(f"Model answer: `{extraction.label}` - model `{extraction.model}`, prompt `{extraction.prompt_version}`, "
             f"recorded {extraction.recorded_at or '-'}")
    if note is not None:
        st.write(f"Draft note: `{note.label}`")
    if extraction.fields is not None:
        st.write("First reading: " + ", ".join(
            f"{LABELS[name]} = {to_text(name, getattr(extraction.fields, name)) or '(none)'}" for name in FIELD_NAMES))
    if result.expected_cents is not None:
        st.write(f"In cents: {result.billed_cents} - {result.expected_cents} = {result.difference_cents}")
    st.write("Finding codes: " + (", ".join(f"`{f.code}`" for f in result.findings) or "none"))
    st.write("Raw model response:")
    st.code(extraction.raw_text or "(no response)", language="json")

store.close()
