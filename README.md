<p align="center"><img src="docs/images/logo.png" alt="Shikhu" width="220"></p>

# Shikhu

**Learn the code your agents write.** Shikhu is a Python CLI for code-aware quizzes, conceptual inquiry, change review and knowledge coverage. Quiz results stay in a local SQLite database.

## Install

Requires Python 3.12+, [`uv`](https://docs.astral.sh/uv/) and Git.

```bash
uv tool install .                     # from this checkout
cd /path/to/your/codebase
shikhu init                           # create a local DB and install optional agent skills
shikhu summarize                      # index tracked source files
shikhu refresh                        # generate questions
shikhu quiz                           # test your understanding
shikhu coverage                       # inspect coverage
shikhu quiz --since main              # review branch changes
```

For an editable development installation: `uv sync --frozen && uv run shikhu --help`.

## Model providers

The original OpenRouter backend remains the default. Set `SHIKHU_PROVIDER` and `SHIKHU_MODEL` to switch all generation paths; non-OpenRouter providers use **uncalibrated heuristic** judgments instead of the specialized Jev scoring API.

| Provider | Required configuration | Inference |
| --- | --- | --- |
| `openrouter` (default) | `OPENROUTER_API_KEY`; optional `SHIKHU_MODEL` | OpenRouter; Jev for judgments |
| `ollama_local` | `SHIKHU_MODEL`; optional `SHIKHU_OLLAMA_URL` | Local/remote Ollama native `/api/chat` |
| `ollama_cloud` | `OLLAMA_API_KEY`, `SHIKHU_MODEL` | `https://ollama.com/api/chat` |
| `bedrock` | `SHIKHU_MODEL`, AWS SDK credentials and Region; `boto3` | AWS Bedrock `Converse` |

**Ollama local:**

```bash
ollama pull qwen3:14b                # choose any local model supporting structured output
export SHIKHU_PROVIDER=ollama_local
export SHIKHU_MODEL=qwen3:14b
# export SHIKHU_OLLAMA_URL=http://100.x.y.z:11434  # optional remote host / Tailscale
shikhu summarize
shikhu refresh
```

**Ollama Cloud:** Its API does not currently support native structured outputs. Shikhu requests JSON in the prompt and validates responses locally; quiz/scoring quality may vary.

```bash
export SHIKHU_PROVIDER=ollama_cloud
export OLLAMA_API_KEY=...            # use a secret manager or ignored .env.local
export SHIKHU_MODEL=gemma4:31b       # confirm current name with https://ollama.com/api/tags
shikhu refresh
```

**Amazon Bedrock:** install the optional SDK with `uv tool install --with boto3 .`, or use `uv run --with boto3 shikhu ...` from the checkout. Configure an AWS profile/role with `bedrock:InvokeModel` for the selected model.

```bash
export SHIKHU_PROVIDER=bedrock
export AWS_PROFILE=your-profile
export AWS_REGION=eu-central-1
export SHIKHU_MODEL=your-bedrock-model-id
shikhu refresh
```

To route judgments through a different model on the same non-OpenRouter provider, set `SHIKHU_JUDGMENT_MODEL`. `SHIKHU_HEURISTIC_BATCH_FILES` sets the non-Jev scoring batch size (default 20). `SHIKHU_REQUEST_TIMEOUT` controls read timeout in seconds (default 120). Bedrock uses native JSON-schema output on supporting Converse models; set `SHIKHU_BEDROCK_STRUCTURED=off` for models without native schema support (JSON then relies on prompting and local validation). Use `shikhu map --dry-run` before scoring past conversations.

## Trust and privacy

- `coverage.db` and `.env.local` are gitignored on `shikhu init`. Store secrets in your shell, a secret manager or `.env.local`; **never commit credentials**.
- Shikhu sends source files, file summaries or selected past prompts to the configured inference provider. **Only `ollama_local` on a trusted server is local-only**. A remote Ollama host is a separate security boundary.
- Non-Jev LLM scores are heuristic values, not calibrated probabilities; scores are tracked separately from Jev results. Do not use them as a security/compliance attestation.
- `shikhu map` may scan local Claude Code transcripts. Review `.quizignore`, model destination and costs before invoking it. Bedrock and cloud providers can incur charges; non-OpenRouter costs are not estimated by Shikhu.
- The git pre-push hook is a local learning check, not a security gate or CI enforcement.

Full CLI reference and learning workflow: [`docs/guide.md`](docs/guide.md). Audit and local deployment notes: [`docs/security-audit.md`](docs/security-audit.md).

MIT-licensed. Original project by [Arjun Patel](https://github.com/arjunpatel7). The upstream repository currently states it is not accepting pull requests.