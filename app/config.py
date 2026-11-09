"""Paths and model settings in one place."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Reference tables: the supplied seeds plus the rows added for this submission.
REFERENCE_FILES = (ROOT / "tasks" / "invoices" / "seed.json", ROOT / "data" / "additions.json")
DOCUMENTS_FILE = ROOT / "data" / "documents.json"  # the batch, in received order
PROMPTS_DIR = ROOT / "prompts"
REPLAY_DIR = ROOT / "replay"  # saved real model responses
DB_PATH = Path(os.environ.get("INVOICE_DB", ROOT / "state" / "review.sqlite"))

# Pinned snapshot, so saved responses stay comparable with new calls.
MODEL = os.environ.get("OPENAI_MODEL") or "gpt-5.4-mini-2026-03-17"
TEMPERATURE = 0
