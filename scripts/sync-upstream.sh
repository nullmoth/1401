#!/usr/bin/env bash
# Fetch and merge upstream nullmoth/1401 into an integration branch, then run the full suite.
# Never rebases, never force-pushes, never pushes. On conflicts or test failure the branch is left
# for a person to resolve; nothing is merged into develop.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain)" ]; then
  echo "Refusing to sync with a dirty working tree. Commit or stash first." >&2
  exit 2
fi

BEFORE=$(git rev-parse upstream/main)
git fetch upstream --tags --prune
AFTER=$(git rev-parse upstream/main)
DATE=$(date +%Y-%m-%d)
BRANCH="integration/upstream-${DATE//-}"

echo "upstream before: $BEFORE"
echo "upstream after:  $AFTER"
echo "new commits:"
git log --oneline "$BEFORE..$AFTER" || true
echo
echo "CHANGELOG/docs changes:"
git diff --stat "$BEFORE..$AFTER" -- CHANGELOG.md docs/ || true

git checkout develop
git checkout -b "$BRANCH"
if ! git merge --no-ff "$AFTER" -m "Sync upstream $(git rev-parse --short "$AFTER")"; then
  echo
  echo "Merge conflicts on $BRANCH. Resolve them, then run:" >&2
  echo "  scripts/run-tests.cmd" >&2
  echo "  git checkout develop && git merge --no-ff $BRANCH" >&2
  exit 3
fi

mkdir -p upstream-notes
REPORT="upstream-notes/sync-${DATE}.md"
{
  echo "# 上游同步 ${DATE}"
  echo
  echo "- 上游 before: \`$BEFORE\`"
  echo "- 上游 after: \`$AFTER\`"
  echo "- 集成分支: \`$BRANCH\`"
  echo "- 新提交:"
  git log --oneline "$BEFORE..$AFTER" | sed 's/^/  - /'
  echo "- 文件变化:"
  git diff --stat "$BEFORE..$AFTER" | tail -40 | sed 's/^/  /'
  echo
  echo "## 测试"
  echo
  echo '（由 scripts/sync-upstream.sh 运行，结果见下方退出状态）'
} > "$REPORT"

echo
echo "Running the full suite on $BRANCH ..."
if ! MSYS_NO_PATHCONV=1 cmd /c 'scripts\run-tests.cmd'; then
  echo "Tests failed on $BRANCH. Nothing was merged into develop. See the output above." >&2
  exit 4
fi

echo
echo "Sync branch $BRANCH is ready. Next, after reviewing the Huawei EFI build:"
echo "  git checkout develop && git merge --no-ff $BRANCH"
echo "  git checkout feature/huawei-1401 && git merge --no-ff develop"
echo "  git push origin develop feature/huawei-1401"
echo "Report: $REPORT"
