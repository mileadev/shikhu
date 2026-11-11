# Security and deployment audit — 2026-11-10

Baseline: [`arjunpatel7/shikhu`](https://github.com/arjunpatel7/shikhu), `main`, Git tree `c102da96d7689923619f933efdec86f41a01e6ab`. Source inspection via GitHub connector; local, offline provider unit tests. Full upstream test suite, dependency-vulnerability scanning and live provider integration tests were **not run** because the sandbox could not clone the full repository and has no API credentials.

## Audit findings

| Severity | Finding | Evidence | Mitigation / status |
| --- | --- | --- | --- |
| High — confidentiality | Generation sends tracked source files to OpenRouter; `map` sends selected local transcript prompts plus file summaries. This is disclosed behavior, but unsuitable for confidential code without review. | `src/shikhu/generator.py`, `transcripts.py`, `commands/map.py` | **Mitigated by choice**: local Ollama backend, explicit provider selection, `.quizignore`, README data-flow warning. Remote Ollama is not automatically private. |
| High — confidentiality | Git-tracked symlinks could resolve outside the repository and be read into prompts. | `src/shikhu/commands/utils.py`, `store.py` | **Fixed**: exclude symlinks from discovery and reject symlink paths at file read. |
| Medium — filesystem | Saved API-key file could be replaced by a symlink, and in-place truncation risks damaging the user config on write failure. | `src/shikhu/env.py` | **Fixed**: reject symlink targets, validate single-line secrets, write via private temporary file and atomic replace. |
| Medium — correctness | Jev's typed calibrated probabilities cannot be reproduced by a standard LLM simply by switching the endpoint. | `src/shikhu/systemone.py`, `inquiry.py` | **Mitigated in integration**: separate uncalibrated heuristic path, strict schema/range validation, model/provider-specific provenance. Quality parity with Jev is not claimed. |
| Medium — secret hygiene | `init` originally warned about an unignored `.env` rather than adding safe defaults to the target repository. | `src/shikhu/commands/init.py` | **Fixed**: ignore `.env`, `.env.local`, `coverage.db*` on initialization; preserve existing ignore rules. Existing tracked secrets still require separate removal and key rotation. |
| Medium — cost control | Jev's process-wide budget check is non-atomic under concurrent `map --workers` calls and can overshoot; it is not a strict transaction-wide billing cap. | `src/shikhu/systemone.py`, `commands/map.py` | **Open**: use `--workers 1` for tighter predictability; use external provider limits; non-OpenRouter prices are not inferred. |
| Medium — untrusted code prompt injection | Provider receives code comments, docs and transcripts as model input; the model can be steered by attacker-controlled project content. | `src/shikhu/generator.py`, `src/shikhu/inquiry.py` | **Partial**: judgment prompt treats context as data; Pydantic/schema validation reduces malformed results. Not a prompt-injection sandbox. |
| Low — voluntary hook | Git pre-push gate can be bypassed locally and should not be described as a mandatory security/compliance control. | `src/shikhu/_hook/pre-push` | **Documented**. Enforce real policy in protected-branch CI instead. |
| Operational | Bedrock `Converse` schema format is model-dependent; Ollama Cloud explicitly lacks native structured outputs. | Official provider documentation | **Mitigated**: native Bedrock schema output with validation, optional prompt-only fallback, local Ollama `format` schema; cloud JSON prompting with validation. Live checks remain required. |

## Verification

- Offline tests for provider selection, no accidental cloud-key forwarding to local Ollama, exact cloud API destination, schema handling, Bedrock request shape, invalid scoring rejection and provenance.
- `python -m compileall` on new modules, `pytest` on new test module.
- Regression check needed after applying onto a full checkout: `uv sync --frozen && uv run ruff check src tests && uv run ruff format --check src tests && uv run pytest tests -q`.
- Integration check requires real models and credentials: `shikhu summarize`, `shikhu refresh`, `shikhu quiz`, `shikhu map --dry-run`, followed by consented `map --yes` on a disposable project.

## Threat model

- Assets: repository code, developer transcripts, API keys, AWS credentials, local knowledge DB.
- Trust boundaries: local CLI → selected inference host; CLI → Git/agent skill folders; CLI → developer prompts/transcripts.
- Controls: provider-specific credentials, no cloud credential forwarded to local Ollama, explicit external data flow, token cap, network timeouts, response validation, ignored local secrets. No claim that local models produce calibrated scoring.

## Rollback

Apply on a clean branch; restore changed paths with `git restore` and remove the newly added modules, tests, `.env.example` and audit file, or discard the branch. Do not delete `coverage.db` without exporting it first.