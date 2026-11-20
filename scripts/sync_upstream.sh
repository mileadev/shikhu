#!/usr/bin/env bash
# Open a review PR when the authoritative Shikhu upstream advances.
# Never pushes to main, force-pushes, or resolves source conflicts automatically.
set -euo pipefail

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Error: tracked working-tree changes. Run from a clean checkout." >&2
  exit 2
fi

UPSTREAM_URL="https://github.com/arjunpatel7/shikhu.git"
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
git fetch --no-tags "$UPSTREAM_URL" refs/heads/main:refs/remotes/shikhu-upstream/main

BASE_SHA="$(git rev-parse refs/remotes/origin/main)"
UPSTREAM_SHA="$(git rev-parse refs/remotes/shikhu-upstream/main)"

if git merge-base --is-ancestor "$UPSTREAM_SHA" "$BASE_SHA"; then
  echo "Fork is already up to date with upstream $UPSTREAM_SHA"
  exit 0
fi

if ! git merge-base "$BASE_SHA" "$UPSTREAM_SHA" >/dev/null; then
  echo "No shared Git history with upstream; refusing unsafe overwrite." >&2
  exit 2
fi

SHORT_SHA="$(git rev-parse --short=12 "$UPSTREAM_SHA")"
BRANCH="sync/upstream-$SHORT_SHA"
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  echo "Branch already exists: $BRANCH. Review its existing PR or remove it manually."
  exit 0
fi

git config user.name "shikhu-upstream-sync"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git switch --create "$BRANCH" "$BASE_SHA"

if ! git merge --no-ff --no-edit -m "chore: merge upstream shikhu $SHORT_SHA" "$UPSTREAM_SHA"; then
  echo "Upstream conflicts require human review. No remote changes were pushed." >&2
  git status --short >&2
  git merge --abort || true
  exit 1
fi

git push --set-upstream origin "HEAD:refs/heads/$BRANCH"
if ! command -v gh >/dev/null 2>&1; then
  echo "gh not installed. Create a pull request manually from $BRANCH."
  exit 0
fi
gh pr create --base main --head "$BRANCH" \
  --title "chore: sync Shikhu upstream $SHORT_SHA" \
  --body "Merges upstream arjunpatel7/shikhu at $UPSTREAM_SHA while preserving our Ollama/Bedrock fork. Requires review: CI tests, provider contracts, changed defaults and new data flows. No automatic merge to main."
