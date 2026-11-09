"""The only module that talks to the model provider (OpenAI Responses API).

Two modes:
  live   - call the model, save the raw response under replay/, label the result "live";
  replay - read the saved response instead, label it "replayed". No API key is needed.
A document can also be marked as a simulated failure: no call is made and the result is
labelled "simulated-failure".

Nothing here raises: every failure comes back as a ModelResult with an error text, so one
bad document cannot stop the batch.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import MODEL, ROOT, TEMPERATURE

LIVE, REPLAYED, SIMULATED_FAILURE = "live", "replayed", "simulated-failure"

SIMULATED_ERRORS = {
    "api_error": "Simulated API failure: the request timed out (no model call was made).",
}


@dataclass
class ModelResult:
    label: str  # live | replayed | simulated-failure
    output_text: str | None = None  # raw model output, exactly as returned
    error: str | None = None
    model: str = MODEL
    prompt_version: str = ""
    recorded_at: str | None = None  # when the real call was made


def input_hash(prompt: str, image_path: Path | None) -> str:
    """Fingerprint of what was sent, so a saved response is never replayed for a changed input."""
    digest = hashlib.sha256(prompt.encode("utf-8"))
    if image_path is not None:
        digest.update(image_path.read_bytes())
    return digest.hexdigest()


def call_openai(prompt: str, image_path: Path | None, schema_name: str, json_schema: dict) -> dict:
    """One real model call. Returns the raw output text plus call details."""
    from dotenv import load_dotenv
    from openai import OpenAI  # imported here: replay mode never needs the SDK or a key

    load_dotenv(ROOT / ".env")
    content = [{"type": "input_text", "text": prompt}]
    if image_path is not None:
        kind = "jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "png"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:image/{kind};base64,{encoded}"})
    response = OpenAI().responses.create(
        model=MODEL,
        temperature=TEMPERATURE,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": json_schema}},
    )
    return {
        "output_text": response.output_text,
        "model": response.model,
        "response_id": response.id,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def run_model(
    mode: str,
    replay_path: Path,
    prompt_version: str,
    prompt: str,
    schema_name: str,
    json_schema: dict,
    image_path: Path | None = None,
    simulate: str | None = None,
) -> ModelResult:
    if simulate is not None:
        error = SIMULATED_ERRORS.get(simulate, f"Simulated failure: {simulate}")
        return ModelResult(label=SIMULATED_FAILURE, error=error, prompt_version=prompt_version)

    label = REPLAYED if mode == "replay" else LIVE
    try:
        fingerprint = input_hash(prompt, image_path)
    except OSError as exc:
        return ModelResult(label=label, error=f"cannot read the image: {exc}", prompt_version=prompt_version)

    if mode == "replay":
        if not replay_path.exists():
            return ModelResult(label=REPLAYED, prompt_version=prompt_version,
                               error=f"no saved response at {replay_path.name}; run live mode to record one")
        saved = json.loads(replay_path.read_text(encoding="utf-8"))
        if saved["input_sha256"] != fingerprint:
            return ModelResult(label=REPLAYED, prompt_version=prompt_version,
                               error="the saved response was recorded for a different image or prompt; "
                                     "run live mode to record a new one")
        return ModelResult(label=REPLAYED, output_text=saved["output_text"], model=saved["model"],
                           prompt_version=saved["prompt_version"], recorded_at=saved["recorded_at"])

    try:
        answer = call_openai(prompt, image_path, schema_name, json_schema)
    except Exception as exc:  # network, authentication, rate limit, bad request...
        return ModelResult(label=LIVE, error=f"model call failed: {type(exc).__name__}: {exc}",
                           prompt_version=prompt_version)

    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "label": LIVE,
        "recorded_at": recorded_at,
        "model": answer["model"],
        "temperature": TEMPERATURE,
        "prompt_version": prompt_version,
        "input_sha256": fingerprint,
        "response_id": answer["response_id"],
        "input_tokens": answer["input_tokens"],
        "output_tokens": answer["output_tokens"],
        "output_text": answer["output_text"],
    }
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    replay_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return ModelResult(label=LIVE, output_text=answer["output_text"], model=answer["model"],
                       prompt_version=prompt_version, recorded_at=recorded_at)
