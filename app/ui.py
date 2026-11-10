"""Review app (Streamlit).

Run:  streamlit run app/ui.py

Written for a reviewer who is not a programmer. There are two screens:

  1. the list   - every invoice as one row: who, one sentence about the result, an Open button;
  2. one invoice - the picture next to what was read from it, then a table that compares the
                   invoice with our records line by line, then one button: checked, next.

The page only shows what is saved in SQLite and what app/reconcile.py calculated. When the
reviewer corrects a value it is saved, everything is recalculated, and the page is drawn again.
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
    "invoice_number": "Invoice number", "supplier_id": "Supplier", "po_id": "Order number",
    "sku": "Item", "quantity": "Quantity", "unit_cents": "Price per unit, $", "total_cents": "Total, $",
}
MONEY_FIELDS = ("unit_cents", "total_cents")

# Plain name and colour for each status.
STATUS_NAMES = {
    "reconciled": ("All good", "green"),
    "discrepant": ("Does not match", "orange"),
    "duplicate": ("Sent twice", "violet"),
    "unresolved": ("Order not found", "blue"),
    "failed": ("Could not read", "red"),
}
# Invoices with something to look at come first, the ones without problems last.
SHOW_ORDER = ["discrepant", "unresolved", "duplicate", "failed", "reconciled"]


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
    return "" if cents is None else format_cents(cents)


def verdict(result: ReconResult) -> str:
    """One plain sentence about the result. Wording only: every fact comes from `result`."""
    if result.status is Status.RECONCILED:
        return "The invoice matches our order and the delivery."
    if result.status is Status.DUPLICATE:
        return "We already received this invoice. It must not be paid twice."
    if result.status is Status.UNRESOLVED:
        return "We cannot find the order this invoice belongs to, so it cannot be checked yet."
    if result.status is Status.FAILED:
        return "This document could not be read."
    if result.difference_cents > 0:
        return f"The supplier asks for {format_cents(result.difference_cents)} more than we agreed."
    if result.difference_cents < 0:
        return f"The supplier asks for {format_cents(-result.difference_cents)} less than we agreed."
    return "The amount is right, but the quantity does not match what was delivered or ordered."


def show_verdict(result: ReconResult) -> None:
    """The verdict as one coloured line: green = fine, yellow = look at it, red = could not read."""
    text = f"**{STATUS_NAMES[result.status.value][0]}.** {verdict(result)}"
    if result.status is Status.RECONCILED:
        st.success(text)
    elif result.status is Status.FAILED:
        st.error(text)
    else:
        st.warning(text)


def title_of(file_id: str, fields) -> str:
    """How an invoice is called on the page: its number and supplier when they could be read."""
    if fields is None or not fields.invoice_number:
        return f"Document '{file_id}'"
    return f"Invoice {fields.invoice_number}" + (f" from {fields.supplier_id}" if fields.supplier_id else "")


# The list is a narrow column; one invoice uses the whole width so the picture is large.
st.set_page_config(page_title="Invoice check", layout="wide" if st.session_state.get("opened") else "centered")
store = Store(DB_PATH)
reference = load_reference()
mode = "live" if st.session_state.get("ask_model_again") else "replay"

if not store.results():  # first start: check everything with the saved model answers
    run_batch("replay", store)
# The same order is used by the list and by the Previous / Next buttons.
results = sorted(store.results(), key=lambda r: SHOW_ORDER.index(r.status.value))
by_id = {r.file_id: r for r in results}
opened = st.session_state.get("opened")


# ====================================================================================
# Screen 1: the list
# ====================================================================================
if opened not in by_id:
    summary = summarize(results)
    checked = sum(1 for r in results if store.review(r.file_id)[0])
    st.title("Invoices")
    st.caption(f"{len(results)} invoices were compared with our orders and deliveries. You checked {checked} of them.")
    if checked == len(results):
        st.success("**All done.** You checked every invoice. Nothing is left to do here.", icon=":material/task_alt:")

    with st.container(horizontal=True):
        st.metric("Overcharged in total", format_cents(summary.recoverable_cents), border=True,
                  help="Only invoices matched to an order are counted. Invoices sent twice or without an order are not.")
        st.metric("Invoices that can be paid", summary.payable_invoices, border=True,
                  help="Invoices matched to an order. Invoices sent twice, unread or without an order are not counted.")

    show = st.pills(
        "Show", ["all"] + SHOW_ORDER, default="all", label_visibility="collapsed",
        format_func=lambda s: f"All ({len(results)})" if s == "all" else f"{STATUS_NAMES[s][0]} ({summary.counts[s]})",
    )
    for result in results:
        if show not in ("all", None, result.status.value):
            continue
        name, colour = STATUS_NAMES[result.status.value]
        with st.container(border=True):
            text, button = st.columns([5, 1], vertical_alignment="center")
            with text:
                with st.container(horizontal=True):
                    st.markdown(f"**{title_of(result.file_id, store.effective_fields(result.file_id))}**")
                    st.badge(name, color=colour)
                    if store.review(result.file_id)[0]:
                        st.badge("checked", icon=":material/check:", color="gray")
                st.caption(verdict(result))
            if button.button("Open", key=f"open-{result.file_id}", width="stretch"):
                st.session_state["opened"] = result.file_id
                st.rerun()

    insight = build_insight(results)
    if insight is not None:
        st.info("**What goes wrong most often.** " + insight.text)

    with st.expander("Settings"):
        st.checkbox("Ask the model again instead of using its saved answers (needs an API key)", key="ask_model_again")
        if st.button("Read all invoices again"):
            run_batch(mode, store)
            st.rerun()
        if st.button("Forget my corrections and start over"):
            store.reset()
            run_batch(mode, store)
            st.rerun()
    store.close()
    st.stop()


# ====================================================================================
# Screen 2: one invoice
# ====================================================================================
file_id = opened
result = by_id[file_id]
extraction = store.extraction(file_id)
current = store.effective_fields(file_id)
document = next(d for d in store.documents() if d["file_id"] == file_id)
corrections = store.corrections(file_id)
reviewed, comment = store.review(file_id)

# --- top row: moving between invoices without going back to the list -----------------
position = results.index(result)
previous_id = results[position - 1].file_id if position > 0 else None
next_id = results[position + 1].file_id if position + 1 < len(results) else None
with st.container(horizontal=True, vertical_alignment="center"):
    if st.button("All invoices", key="back", icon=":material/list:"):
        del st.session_state["opened"]
        st.rerun()
    if st.button("Previous", key="previous", icon=":material/arrow_back:", disabled=previous_id is None):
        st.session_state["opened"] = previous_id
        st.rerun()
    if st.button("Next", key="next", icon=":material/arrow_forward:", disabled=next_id is None):
        st.session_state["opened"] = next_id
        st.rerun()
    st.caption(f"{position + 1} of {len(results)}" + ("  -  you already checked this one" if reviewed else ""))

st.header(title_of(file_id, current))
show_verdict(result)

# --- 1. is the invoice read correctly? ----------------------------------------------
with st.container(border=True):
    st.subheader("1. Was the invoice read correctly?")
    st.caption("Left: the invoice. Right: what the computer read from it. If a box is wrong, type what the invoice says.")
    left, right = st.columns([3, 2])
    with left:
        image_path = ROOT / document["image"]
        if image_path.exists():
            st.image(str(image_path), width="stretch")
        else:
            st.error(f"Picture not found: {document['image']}")
    with right:
        if extraction.error:
            st.error(f"The computer could not read this document: {extraction.error}")
        with st.form(f"correct-{file_id}", border=False):
            typed = {
                field: st.text_input(LABELS[field], value=to_text(field, getattr(current, field)) if current else "",
                                     key=f"{file_id}-{field}")
                for field in FIELD_NAMES
            }
            if st.form_submit_button("Save and check again"):
                try:
                    new_values = {field: from_text(field, text) for field, text in typed.items()}
                    changed = {field: value for field, value in new_values.items()
                               if value != (getattr(current, field) if current else None)}
                    for field, value in changed.items():
                        store.add_correction(file_id, field, value)
                except ValueError as exc:
                    st.error(f"Not saved: {exc}")
                else:
                    if changed:
                        draft_notes(store, recompute(store, reference), mode, only_changed=True)
                        st.rerun()
                    st.info("Nothing was changed.")
    if corrections:
        st.caption("You corrected:")
        st.table([{
            "what": LABELS[c["field"]],
            "the computer read": to_text(c["field"], json.loads(c["old_value"])),
            "you corrected to": to_text(c["field"], json.loads(c["new_value"])),
        } for c in corrections])

# --- 2. the comparison --------------------------------------------------------------
with st.container(border=True):
    st.subheader("2. Does it match our records?")
    if result.expected_cents is not None:
        order = next(po for po in reference.purchase_orders if po.po_id == result.po_id)
        lines = [
            ("Item", current.sku, order.sku, "what we ordered"),
            ("Price per unit", money(current.unit_cents), money(result.agreed_unit_cents), "the price we agreed"),
            ("Quantity", str(current.quantity), str(result.ordered_qty), "how many we ordered"),
            ("Quantity", str(current.quantity), str(result.received_qty), "how many actually arrived"),
            ("Total to pay", money(result.billed_cents), money(result.expected_cents), "ordered quantity x agreed price"),
        ]
        st.table([{
            "": what,
            "the invoice says": on_invoice,
            f"our records (order {order.po_id})": f"{ours} - {meaning}",
            "same?": "✅ yes" if on_invoice.strip().lower() == ours.strip().lower() else "❌ no",
        } for what, on_invoice, ours, meaning in lines])
        st.markdown(f"Difference in the total: **{format_cents(result.difference_cents)}**")
    for finding in result.findings:
        st.markdown(f"- {finding.message}")
    if not result.findings:
        st.write("No problems found.")

    note = store.note(file_id)
    if note is not None:
        st.divider()
        st.markdown("**Suggested message** - a draft written by the computer from the facts above. Read it before you use it.")
        if note.error:
            st.warning(f"No draft is available: {note.error}")
        elif current is not None and note.facts_hash != facts_hash(result, current):
            st.warning("The result changed after this draft was written. Use 'Read all invoices again' in Settings.")
        else:
            st.info(note.text)

# --- 3. done ------------------------------------------------------------------------
# Pressing the button is the check mark: it saves "checked" with the comment and opens the next invoice.
with st.form(f"review-{file_id}"):
    st.subheader("3. Done")
    new_comment = st.text_input("Comment (optional)", value=comment, key=f"{file_id}-comment")
    with st.container(horizontal=True):
        done = st.form_submit_button("Checked - next invoice", type="primary", icon=":material/check:")
        undo = st.form_submit_button("Not checked yet") if reviewed else False
    if done or undo:
        store.save_review(file_id, bool(done), new_comment)
        if done:
            # Open the next invoice that is not checked yet: first the ones after this one, then the ones before.
            others = results[position + 1:] + results[:position]
            not_checked = [r.file_id for r in others if not store.review(r.file_id)[0]]
            if not_checked:
                st.session_state["opened"] = not_checked[0]
            else:
                del st.session_state["opened"]  # everything is checked: back to the list, which says so
        st.rerun()

# --- technical details, for inspecting a failure -------------------------------------
with st.expander("Technical details"):
    st.write(f"File `{file_id}` ({document['image']}), status `{result.status.value}`")
    st.write(f"Model answer: `{extraction.label}` - model `{extraction.model}`, prompt `{extraction.prompt_version}`, "
             f"recorded {extraction.recorded_at or '-'}")
    if note is not None:
        st.write(f"Draft note: `{note.label}`")
    if extraction.fields is not None:
        st.write("First reading: " + ", ".join(
            f"{LABELS[field]} = {to_text(field, getattr(extraction.fields, field)) or '(none)'}" for field in FIELD_NAMES))
    if result.expected_cents is not None:
        st.write(f"Matched records: {result.po_id}, {', '.join(result.receipt_ids) or 'no receipt'}. "
                 f"In cents: {result.billed_cents} - {result.expected_cents} = {result.difference_cents}")
    st.write("Finding codes: " + (", ".join(f"`{f.code}`" for f in result.findings) or "none"))
    st.write("Raw model response:")
    st.code(extraction.raw_text or "(no response)", language="json")

store.close()
