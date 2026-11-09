"""SQLite state: documents, original extractions, reviewer corrections and results.

The original extraction is never changed. A reviewer correction is a separate row; the
"effective" fields used for reconciliation are the original fields with the corrections
applied on top, in the order they were made. Everything is in one file, so it survives a
restart.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.extract import Extraction
from app.models import InvoiceFields
from app.reconcile import Finding, ReconResult, Status

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    file_id TEXT PRIMARY KEY, position INTEGER NOT NULL, image TEXT NOT NULL, image_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS extractions (
    file_id TEXT PRIMARY KEY, label TEXT NOT NULL, fields_json TEXT, error TEXT, raw_text TEXT,
    model TEXT, prompt_version TEXT, recorded_at TEXT
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL, field TEXT NOT NULL,
    old_value TEXT, new_value TEXT, corrected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    file_id TEXT PRIMARY KEY, status TEXT NOT NULL, result_json TEXT NOT NULL, computed_at TEXT NOT NULL
);
"""

FIELD_NAMES = tuple(InvoiceFields.model_fields)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def reset(self) -> None:
        """Forget everything, including reviewer corrections."""
        for table in ("documents", "extractions", "corrections", "results"):
            self.db.execute(f"DELETE FROM {table}")
        self.db.commit()

    # --- documents and extractions -------------------------------------------------

    def save_document(self, file_id: str, position: int, image: str, image_sha256: str | None) -> bool:
        """Save a batch document. Returns True if old corrections were dropped because the image changed."""
        old = self.db.execute("SELECT image_sha256 FROM documents WHERE file_id = ?", (file_id,)).fetchone()
        dropped = False
        if old is not None and old["image_sha256"] != image_sha256:
            dropped = self.db.execute("DELETE FROM corrections WHERE file_id = ?", (file_id,)).rowcount > 0
        self.db.execute("INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?)", (file_id, position, image, image_sha256))
        self.db.commit()
        return dropped

    def remove_documents_not_in(self, file_ids: list[str]) -> None:
        for (file_id,) in self.db.execute("SELECT file_id FROM documents").fetchall():
            if file_id not in file_ids:
                for table in ("documents", "extractions", "corrections", "results"):
                    self.db.execute(f"DELETE FROM {table} WHERE file_id = ?", (file_id,))
        self.db.commit()

    def documents(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM documents ORDER BY position").fetchall()

    def save_extraction(self, ext: Extraction) -> None:
        fields_json = None if ext.fields is None else ext.fields.model_dump_json()
        self.db.execute(
            "INSERT OR REPLACE INTO extractions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ext.file_id, ext.label, fields_json, ext.error, ext.raw_text, ext.model, ext.prompt_version, ext.recorded_at),
        )
        self.db.commit()

    def extraction(self, file_id: str) -> Extraction | None:
        row = self.db.execute("SELECT * FROM extractions WHERE file_id = ?", (file_id,)).fetchone()
        if row is None:
            return None
        fields = None if row["fields_json"] is None else InvoiceFields.model_validate_json(row["fields_json"])
        return Extraction(
            file_id=file_id, label=row["label"], fields=fields, error=row["error"], raw_text=row["raw_text"],
            model=row["model"], prompt_version=row["prompt_version"], recorded_at=row["recorded_at"],
        )

    # --- reviewer corrections ------------------------------------------------------

    def add_correction(self, file_id: str, field: str, new_value) -> None:
        """Record one corrected field. `new_value` is text, a whole number (quantity, cents) or None."""
        if field not in FIELD_NAMES:
            raise ValueError(f"unknown field: {field}")
        current = self.effective_fields(file_id) or InvoiceFields()
        # Validate the new value before saving it (for example, no negative quantity).
        InvoiceFields.model_validate({**current.model_dump(), field: new_value})
        self.db.execute(
            "INSERT INTO corrections (file_id, field, old_value, new_value, corrected_at) VALUES (?, ?, ?, ?, ?)",
            (file_id, field, json.dumps(getattr(current, field)), json.dumps(new_value), _now()),
        )
        self.db.commit()

    def corrections(self, file_id: str) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM corrections WHERE file_id = ? ORDER BY id", (file_id,)).fetchall()

    def effective_fields(self, file_id: str) -> InvoiceFields | None:
        """Original extraction plus corrections. None when extraction failed and nothing was corrected."""
        ext = self.extraction(file_id)
        fixes = self.corrections(file_id)
        if (ext is None or ext.fields is None) and not fixes:
            return None
        values = ext.fields.model_dump() if ext is not None and ext.fields is not None else {}
        for fix in fixes:
            values[fix["field"]] = json.loads(fix["new_value"])
        return InvoiceFields.model_validate(values)

    # --- results -------------------------------------------------------------------

    def save_results(self, results: list[ReconResult]) -> None:
        self.db.execute("DELETE FROM results")
        for result in results:
            self.db.execute(
                "INSERT INTO results VALUES (?, ?, ?, ?)",
                (result.file_id, result.status.value, json.dumps(asdict(result)), _now()),
            )
        self.db.commit()

    def results(self) -> list[ReconResult]:
        """Saved results in batch order."""
        rows = self.db.execute(
            "SELECT r.result_json FROM results r JOIN documents d ON d.file_id = r.file_id ORDER BY d.position"
        ).fetchall()
        out = []
        for row in rows:
            data = json.loads(row["result_json"])
            data["status"] = Status(data["status"])
            data["findings"] = [Finding(**f) for f in data["findings"]]
            out.append(ReconResult(**data))
        return out
