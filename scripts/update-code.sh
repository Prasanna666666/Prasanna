#!/bin/bash
# Brings the local `atlas` branch up to the newest version on the remote, and never puts the owner's own work at risk:
#   - a dirty working folder (uncommitted changes) is refused, nothing is touched
#   - local commits that are not on origin/atlas (ahead or diverged) are refused, nothing is moved
#   - otherwise the branch is moved forward only (fast-forward), after a tag marks where it was
# The folder is ATLAS_REPO, or the folder above this script.
set -euo pipefail
cd "${ATLAS_REPO:-$(dirname "$0")/..}"
BRANCH="${ATLAS_BRANCH:-atlas}"
git fetch origin
if [ -n "$(git status --porcelain)" ]; then
  echo "Not updated: you have changes that are not saved in a commit." >&2
  echo "Save them (git commit), or put them aside (git stash), then run ./update.sh again. Nothing was changed." >&2
  exit 1
fi
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  ahead="$(git rev-list --count "origin/$BRANCH..$BRANCH")"
  if [ "$ahead" != 0 ]; then
    echo "Not updated: your $BRANCH has $ahead commit(s) that are not on the server, so moving it would hide them." >&2
    echo "Keep them with: git branch my-work-$(date +%Y%m%d)   then ask for help to combine them. Nothing was changed." >&2
    exit 1
  fi
  git tag -f "$BRANCH-before-update-$(date +%Y%m%d-%H%M%S)" "$BRANCH" >/dev/null   # marks where it was
  git checkout "$BRANCH"
  git merge --ff-only "origin/$BRANCH"
else
  git checkout -b "$BRANCH" "origin/$BRANCH"
fi
