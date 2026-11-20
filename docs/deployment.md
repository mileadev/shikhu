# Deployment and upstream upgrades

This is [mileadev/shikhu](https://github.com/mileadev/shikhu), a fork of
[arjunpatel7/shikhu](https://github.com/arjunpatel7/shikhu).
The fork preserves upstream Git ancestry and the optional inference providers.

## Install the fork

Requires Python 3.12+, Git and uv.

```bash
uv tool install --force --python 3.12 "git+https://github.com/mileadev/shikhu.git@main"
```

Install Bedrock support by adding `--with boto3` before the Git URL.
Run in any target Git repository:

```bash
export SHIKHU_PROVIDER=ollama_local SHIKHU_MODEL=qwen3:14b
shikhu init --no-skill
shikhu refresh
shikhu quiz
```

Or select `ollama_cloud` with `OLLAMA_API_KEY`, or `bedrock` with a scoped
AWS role/profile and an approved model. Review `.quizignore` before sharing
source code with any remote inference provider.

## Tracking upstream safely

- Source: `arjunpatel7/shikhu:main`.
- Trigger: GitHub Actions [upstream-sync.yml](../.github/workflows/upstream-sync.yml),
  weekly or manually via **Actions**.
- Behavior: fetch upstream, merge on a new `sync/upstream-<sha>` branch,
  create a **review PR**; never force-push or auto-merge `main`.
- Conflicts: workflow stops without a remote push. Resolve in a local branch,
  run CI, and open a human-reviewed PR.
- Review: `generator._chat` dispatch, `systemone.ask` return contract,
  Pydantic response schemas, config loading, source data boundaries,
  dependency/lockfile changes and model defaults.
- Repository settings may require enabling Actions and allowing GitHub Actions
  to create pull requests.

A local equivalent is `bash scripts/sync_upstream.sh` from a clean checkout
with writable GitHub origin and GitHub CLI authentication.

## Validation (required before merging an upstream upgrade)

```bash
uv sync --frozen
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
uv build --wheel
```

Smoke-test `shikhu init --no-skill`, `shikhu refresh`, `shikhu quiz`, and
`shikhu map --dry-run` on a disposable nonsecret repository for each enabled
provider. Mocked tests cannot prove live API compatibility.

## Rollback

Record the last tested SHA and reinstall it with
`uv tool install --force "git+https://github.com/mileadev/shikhu.git@<sha>"`.
Never delete the user's `coverage.db` or replace the fork's `main` with
upstream commits by force.
