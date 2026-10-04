#!/usr/bin/env bash
#
# Merge a new upstream Synapse release into SynACK.
#
# Usage: scripts-dev/synack-sync-upstream.sh <upstream-tag>     e.g. v1.162.0
#        scripts-dev/synack-sync-upstream.sh --status
#
# The merge is always based on the last unmodified upstream release we merged
# (recorded in .synack/UPSTREAM_BASE), so that "what upstream changed" and
# "what SynACK changed" are both measured from the same stock tree.
# See SYNACK.md for the full procedure.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

BASE_FILE=.synack/UPSTREAM_BASE
UPSTREAM_REMOTE=${SYNACK_UPSTREAM_REMOTE:-upstream}
UPSTREAM_URL=https://github.com/element-hq/synapse.git
# Files that only exist in SynACK and are never part of an upstream comparison.
FORK_ONLY=(':!README.md' ':!SYNACK.md' ':!.synack' ':!scripts-dev/synack-sync-upstream.sh')

base_tag=$(sed -n 's/^tag: //p' "$BASE_FILE")
base_commit=$(sed -n 's/^commit: //p' "$BASE_FILE")

if [[ "${1:-}" == "--status" ]]; then
    echo "Upstream base: $base_tag ($base_commit)"
    echo
    echo "SynACK changes relative to stock Synapse $base_tag:"
    git diff --stat "$base_commit" HEAD -- . "${FORK_ONLY[@]}"
    exit 0
fi

new_tag=${1:?usage: $0 <upstream-tag> | --status}

if [[ -n "$(git status --porcelain)" ]]; then
    echo "error: the working tree is not clean; commit or stash first" >&2
    exit 1
fi

git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1 ||
    git remote add "$UPSTREAM_REMOTE" "$UPSTREAM_URL"
git fetch --no-tags "$UPSTREAM_REMOTE" "refs/tags/$new_tag:refs/tags/$new_tag"
new_commit=$(git rev-parse "$new_tag^{commit}")

out=$(git rev-parse --git-dir)/synack-sync
mkdir -p "$out"
git diff --name-only "$base_commit" "$new_commit" | sort >"$out/upstream-changes"
git diff --name-only "$base_commit" HEAD -- . "${FORK_ONLY[@]}" | sort >"$out/synack-changes"
comm -12 "$out/upstream-changes" "$out/synack-changes" >"$out/overlap"

echo "Upstream $base_tag -> $new_tag: $(wc -l <"$out/upstream-changes") files changed"
echo "SynACK changes on top of $base_tag: $(wc -l <"$out/synack-changes") files"
echo "Files changed by both ($(wc -l <"$out/overlap")):"
sed 's/^/    /' "$out/overlap"
echo

# Merge with the recorded upstream base as the explicit merge base. For a
# normal release this is what git would pick anyway; being explicit keeps the
# merge correct if upstream's tags ever stop being linear.
set +e
git merge-recursive "$base_commit" -- HEAD "$new_commit"
merge_status=$?
set -e
printf '%s\n' "$new_commit" >"$(git rev-parse --git-dir)/MERGE_HEAD"
printf 'Merge Synapse %s\n' "$new_tag" >"$(git rev-parse --git-dir)/MERGE_MSG"
printf 'no-ff\n' >"$(git rev-parse --git-dir)/MERGE_MODE"

printf 'tag: %s\ncommit: %s\n' "$new_tag" "$new_commit" >"$BASE_FILE"
git add "$BASE_FILE"

echo
if [[ $merge_status -ne 0 ]]; then
    echo "Conflicts need resolving (git status). For each file compare:"
else
    echo "Merged without conflicts. Still review each overlapping file:"
fi
cat <<EOF
    upstream's change:  git diff $base_commit $new_commit -- <path>
    SynACK's change:    git diff $base_commit HEAD -- <path>
Then run the media tests, update the README if a patch was dropped, and
commit. The lists are in $out/.
To back out: git merge --abort
EOF
