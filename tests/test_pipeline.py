"""Extraction, replay, storage and the batch run. No test here calls the model:
they use the saved real responses in replay/ or small fake responses written to a temp folder.
"""
import json
import subprocess
import sys

import pytest

from app import llm
from app.config import ROOT
from app.extract import JSON_SCHEMA, ExtractionError, RawExtraction, extract_invoice, load_prompt, parse_output
from app.reconcile import Status, summarize
from app.reference import load_reference
from app.run import load_documents, recompute, run_batch
from app.store import Store

EXPECTED = json.loads((ROOT / "data" / "expected-results.json").read_text(encoding="utf-8"))
KEYS = ("status", "po_id", "expected_cents", "difference_cents", "duplicate_of")


def as_row(result) -> dict:
    return {"status": result.status.value, "po_id": result.po_id, "expected_cents": result.expected_cents,
            "difference_cents": result.difference_cents, "duplicate_of": result.duplicate_of}


def expected_row(row: dict) -> dict:
    return {key: row.get(key) for key in KEYS}


def summary_dict(results) -> dict:
    s = summarize(results)
    return {"counts": s.counts, "recoverable_cents": s.recoverable_cents, "payable_invoices": s.payable_invoices}


def expected_summary(block: dict) -> dict:
    return {key: block[key] for key in ("counts", "recoverable_cents", "payable_invoices")}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "review.sqlite")
    yield s
    s.close()


# --- parsing the model output ------------------------------------------------------

def test_schema_and_pydantic_model_have_the_same_fields():
    assert list(JSON_SCHEMA["properties"]) == list(RawExtraction.model_fields) == JSON_SCHEMA["required"]


def test_parse_output_converts_printed_text_to_cents():
    fields = parse_output('{"invoice_number":"INV-2","supplier_id":"S1","po_id":"PO-2","sku":"CAB-1",'
                          '"quantity":"5","unit_price":"24.00","total":"$120.00"}')
    assert (fields.quantity, fields.unit_cents, fields.total_cents) == (5, 2400, 12000)


@pytest.mark.parametrize("text, message", [
    ("not json at all", "does not match the schema"),
    ('{"invoice_number":"INV-1"}', "does not match the schema"),
    ('{"invoice_number":"INV-1","supplier_id":"S1","po_id":"PO-1","sku":"CAB-1","quantity":"five",'
     '"unit_price":"20.00","total":"100.00"}', "quantity is not a whole number"),
    ('{"invoice_number":"INV-1","supplier_id":"S1","po_id":"PO-1","sku":"CAB-1","quantity":"5",'
     '"unit_price":"20.005","total":"100.00"}', "fractions of a cent"),
    ('{"invoice_number":null,"supplier_id":null,"po_id":null,"sku":null,"quantity":null,'
     '"unit_price":null,"total":null}', "could not read any invoice field"),
])
def test_bad_model_output_is_a_readable_error(text, message):
    with pytest.raises(ExtractionError, match=message):
        parse_output(text)


# --- replay ------------------------------------------------------------------------

def write_fake_response(replay_dir, file_id, image_path, output_text):
    record = {"output_text": output_text, "model": "fake", "prompt_version": "test", "recorded_at": None,
              "input_sha256": llm.input_hash(load_prompt(), image_path)}
    path = replay_dir / "extract" / f"{file_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")


def test_replay_refuses_a_response_recorded_for_another_image(tmp_path):
    clean = ROOT / "tasks/invoices/images/clean.png"
    write_fake_response(tmp_path, "x", clean, "{}")
    other = extract_invoice("x", ROOT / "tasks/invoices/images/wrong-price.png", "replay", replay_dir=tmp_path)
    assert other.fields is None and "different image or prompt" in other.error


def test_missing_replay_file_and_missing_image_are_errors_not_crashes(tmp_path):
    no_file = extract_invoice("x", ROOT / "tasks/invoices/images/clean.png", "replay", replay_dir=tmp_path)
    assert "no saved response" in no_file.error
    no_image = extract_invoice("x", tmp_path / "nothing.png", "replay", replay_dir=tmp_path)
    assert "cannot read the image" in no_image.error


def test_live_api_error_is_returned_not_raised(tmp_path, monkeypatch):
    def broken_call(*args, **kwargs):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(llm, "call_openai", broken_call)
    result = extract_invoice("x", ROOT / "tasks/invoices/images/clean.png", "live", replay_dir=tmp_path)
    assert result.label == "live" and "TimeoutError" in result.error
    assert not (tmp_path / "extract" / "x.json").exists()  # failures are never saved as responses


def test_one_bad_document_does_not_stop_the_batch(tmp_path, store):
    """Invalid JSON for the first document; the second one is still processed."""
    docs = [{"file_id": "broken", "image": "tasks/invoices/images/clean.png"},
            {"file_id": "good", "image": "tasks/invoices/images/wrong-price.png"},
            {"file_id": "sim", "image": "tasks/invoices/images/duplicate.png", "simulate": "api_error"}]
    write_fake_response(tmp_path, "broken", ROOT / docs[0]["image"], '{"invoice_number": "INV-1"')
    write_fake_response(tmp_path, "good", ROOT / docs[1]["image"],
                        '{"invoice_number":"INV-2","supplier_id":"S1","po_id":"PO-2","sku":"CAB-1",'
                        '"quantity":"5","unit_price":"24.00","total":"120.00"}')
    results = run_batch("replay", store, documents=docs, replay_dir=tmp_path)
    assert [r.status for r in results] == [Status.FAILED, Status.DISCREPANT, Status.FAILED]
    assert "does not match the schema" in results[0].findings[0].message
    assert store.extraction("sim").label == "simulated-failure"
    assert results[1].difference_cents == 2000


# --- the real batch, replayed from the saved model responses ------------------------

def test_replayed_batch_against_the_hand_written_answer_key(store):
    """The saved real responses, compared with data/expected-results.json.

    Known model error (docs/DEVLOG.md, day 2): the invoice `po-typo` prints "P0-4" (digit zero)
    but the model returns "PO-4". So before any review the app's result for that document is
    the answer key's "PO-4" scenario, not the "unresolved" row. Every other document must match.
    """
    results = run_batch("replay", store)
    labels = {doc["file_id"]: store.extraction(doc["file_id"]).label for doc in load_documents()}
    assert set(labels.values()) == {"replayed", "simulated-failure"}

    for result, row in zip(results, EXPECTED["documents"], strict=True):
        if result.file_id != "po-typo":
            assert as_row(result) == expected_row(row), result.file_id
    assert store.extraction("po-typo").fields.po_id == "PO-4"  # the recorded misread
    assert summary_dict(results) == expected_summary(EXPECTED["after_correction"]["summary"])


def test_reviewer_correction_reruns_and_survives_a_restart(tmp_path):
    """The reviewer corrects the misread reference to what is printed (P0-4) and the batch is recalculated."""
    path = tmp_path / "review.sqlite"
    store = Store(path)
    run_batch("replay", store)
    store.add_correction("po-typo", "po_id", "P0-4")
    results = recompute(store, load_reference())
    for result, row in zip(results, EXPECTED["documents"], strict=True):
        assert as_row(result) == expected_row(row), result.file_id
    assert summary_dict(results) == expected_summary(EXPECTED["summary"])
    store.close()

    reopened = Store(path)  # "restart"
    assert reopened.extraction("po-typo").fields.po_id == "PO-4"  # the original extraction is kept
    assert reopened.effective_fields("po-typo").po_id == "P0-4"
    fix = reopened.corrections("po-typo")[0]
    assert (fix["field"], json.loads(fix["old_value"]), json.loads(fix["new_value"])) == ("po_id", "PO-4", "P0-4")
    assert [as_row(r) for r in reopened.results()] == [as_row(r) for r in results]

    # A new replay run keeps the correction (only --reset or a changed image drops it).
    again = run_batch("replay", reopened)
    assert summary_dict(again) == expected_summary(EXPECTED["summary"])
    reopened.close()


def test_correcting_a_failed_document_makes_it_reconcilable(store):
    run_batch("replay", store)
    typed = {"invoice_number": "INV-7", "supplier_id": "S2", "po_id": "PO-5", "sku": "SW-1",
             "quantity": 2, "unit_cents": 4500, "total_cents": 9000}
    for field, value in typed.items():
        store.add_correction("api-error", field, value)
    result = {r.file_id: r for r in recompute(store, load_reference())}["api-error"]
    assert (result.status, result.expected_cents, result.difference_cents) == (Status.RECONCILED, 9000, 0)


def test_invalid_correction_is_rejected(store):
    run_batch("replay", store)
    with pytest.raises(ValueError):
        store.add_correction("clean", "quantity", -1)
    with pytest.raises(ValueError):
        store.add_correction("clean", "colour", "red")
    assert store.corrections("clean") == []


def test_answer_key_checker_passes():
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_expected.py")], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
