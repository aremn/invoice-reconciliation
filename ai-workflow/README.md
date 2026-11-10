# AI workflow used during this exercise

The machine-readable list is `manifest.json` in this folder. This file explains it.

## Tools and models

**Development (writing the code)**

| Tool | Version / model | Settings changed |
|---|---|---|
| Claude Code, Claude desktop app (Code tab), Windows 11 | 2.1.309 | none |
| Development model | Claude Fable 5.2 (`claude-fable-5-2`) | reasoning effort lowered from extra-high to medium during day 2 to save usage |

Claude Code generated the application code, the tests, the added invoices and most of the
documentation. The model of the first short session that drafted the project folder and
`CLAUDE.md` was not recorded.

**Application (inside the product)**

| Setting | Value | Where |
|---|---|---|
| Provider, API | OpenAI, Responses API with image input | `app/llm.py` |
| Model | `gpt-5.4-mini-2026-03-17` (pinned snapshot) | `app/config.py`, `.env.example` |
| Temperature | 0 | `app/config.py` |
| Output | strict JSON schema, then Pydantic validation | `app/extract.py`, `app/notes.py` |
| Image detail, output limit | provider defaults | - |

The model was chosen on day 1 from three configurations tried on the same invoice image
(`docs/DEVLOG.md`, "Model choice").

## Configuration files

| Component | Path | Status |
|---|---|---|
| Agent instructions | `CLAUDE.md` (versions in Git history) | used |
| Data-generation skill from the starter pack | `.claude/skills/generate-assignment-data/SKILL.md` | used once, day 2 |
| Extraction prompt | `prompts/extract_invoice_v1.txt` | used |
| Extraction prompt, earlier experiment | `prompts/extract_invoice_v2.txt` + `replay/history/` | tried, dropped |
| Note prompt | `prompts/draft_note_v1.txt` | used |
| Domain rules | `tasks/invoices/domain.md` | supplied, unchanged |
| Preview start command for the desktop app | `.claude/launch.json` | used |
| Environment variable names | `.env.example` | key value redacted |
| Subagents, hooks, plugins | - | not-used |
| Project permission file | - | default: calls were approved in the app, not exportable |
| User-level skill `developing-with-streamlit` | not copied; reads docs bundled with Streamlit 1.67.0 | not-exportable |
| User-level settings, one memory note, reminders | not copied | not-exportable, unrelated to what the code does |

Nothing has to be restored to run the project. To continue development with the same setup, open
the repository in Claude Code: `CLAUDE.md`, the skill and `launch.json` are read from their normal
locations.

Redactions: the only secret is the OpenAI key. It lives in a local `.env` (git-ignored); the
repository has the variable name with an empty value.

## One workflow example

**Instruction.** The task for day 1 was the reconciliation core. The rules that shaped it are in
`CLAUDE.md`:

> Keep `reconcile.py` small and fully unit-tested. It is the part reviewers will probe.
> Run `pytest` before saying a step is done. Report failures honestly; do not weaken tests to pass.

**Output.** `app/reconcile.py` and 30 tests. All 30 passed on the first run.

**Check.** Passing tests written by the same tool that wrote the code prove little, so the rules
were broken on purpose, one at a time, to see whether a test notices:

| Deliberate break | Result |
|---|---|
| expected amount from billed instead of ordered quantity | caught |
| supplier check removed from matching | caught |
| undercharges counted as recoverable | **not caught - all 30 tests passed** |

**Correction.** `test_undercharge_is_discrepant_but_not_recoverable` was added; the same break
now fails it. Recorded in `docs/DEVLOG.md`, day 1.

Two more real cases are in the dev log: the model read the printed `P0-4` as `PO-4` (caught by
the hand-written answer key, not fixable by prompt, image detail or a larger model, so documented
and used as the correction demo), and the generated note checker rejected two correct notes
because of a comma (caught by reading the batch output, fixed, tests added).

## One setting and how its effect was checked

**Temperature 0.** The expectation was repeatable answers. Checked by comparing saved responses of
separate live runs (`git diff replay/`): the extracted fields were identical in three runs, but a
second live run reworded all six draft notes. Conclusion: temperature 0 reduces variation, it does
not remove it. So every real response is saved and replayed, and the note check runs on every
response.

## Reproduce or replay

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m pytest -q                         # no key, no model calls
.venv/Scripts/python -m app.run --mode replay --reset     # saved real responses, no key
.venv/Scripts/python -m streamlit run app/ui.py           # review page, replay by default
```

Each result is labelled `replayed`, `live` or `simulated-failure`. A saved response stores a hash
of its prompt and image, and replay refuses to use it for a different input. Live mode
(`--mode live`, needs `OPENAI_API_KEY` in `.env`) calls the model again and overwrites `replay/`.

There are no hooks, so nothing runs automatically.

## Decisions and limitations

- A default setup was enough: one instruction file, the supplied skill, three prompts. No agents
  or hooks were created because nothing in the task needed them.
- `CLAUDE.md` did the most work. Writing the non-negotiable rules first (model only reads and
  writes text, integer cents, exact matching, independent answer key) kept the generated code
  inside them without repeating the rules in every request.
- What I would change: record the development model and effort at the start of every session,
  and write the answer key before the first line of application code, not on day 2.
- Complete chat logs are not included.
