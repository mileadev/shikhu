# Shikhu local-provider integration overlay

This archive is a pinned source overlay for `arjunpatel7/shikhu` at upstream Git tree `c102da96d7689923619f933efdec86f41a01e6ab`. It is **not** a pre-cloned Git repository. `apply_patch.py` refuses to modify a checkout if the tracked source files differ from the audited Git blobs.

## Apply and verify

```bash
git clone https://github.com/arjunpatel7/shikhu.git
cd shikhu
git switch -c feat/ollama-bedrock-local
python3 /path/to/shikhu-overlay/apply_patch.py .
uv sync --frozen
uv run ruff format src tests
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest tests -q
uv run shikhu --help
git diff --check
```

Review `git diff` before committing. The upstream repo explicitly says it is not accepting PRs, and the connected GitHub account currently has no upstream push permission. To publish, make a writable fork, add it as your remote, commit and push the branch there; do not force-push to upstream.

## Run locally

```bash
ollama pull qwen3:14b
export SHIKHU_PROVIDER=ollama_local
export SHIKHU_MODEL=qwen3:14b
# Optional for a trusted remote GPU host:
# export SHIKHU_OLLAMA_URL=http://100.x.y.z:11434
uv run shikhu init --no-skill
uv run shikhu summarize
uv run shikhu refresh
uv run shikhu quiz
uv run shikhu map --dry-run
```

`init` creates a private local database and modifies only the target repo's `.gitignore` and `.quizignore` plus optional skills/hooks. Perform a real provider smoke test in a disposable Git repository containing small, nonsecret code first. For Bedrock, install the optional `boto3` SDK via `uv run --with boto3 shikhu ...`, configure an AWS profile/role with `bedrock:InvokeModel` and a permitted model ID, and verify regional availability. Bedrock/Ollama Cloud can incur charges; use `map --dry-run` before `map --yes`.

## Verification status

- Offline provider API-mock tests: 15 passed.
- Python compile check: passed.
- Real provider requests: not executed (no credentials/models available).
- Full upstream regression suite and Ruff CI: not executed (full upstream checkout unavailable in this runtime).
- Upstream push: not performed (read-only connected GitHub permissions).

**Limitations:** Ollama Cloud has no native structured-output support; this adapter prompts for JSON and validates locally. Non-Jev judgments are heuristics and do not have Jev's calibration. See `docs/security-audit.md` for risks and verification gaps.