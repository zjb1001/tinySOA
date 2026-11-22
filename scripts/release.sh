#!/usr/bin/env bash
# Local release (CD) scaffold for tinySOA.
#
# It runs the local CI gate, creates an annotated tag, and optionally pushes the
# tag and creates a GitHub Release. There is no deployment target in this repo;
# "release" means a tagged, verified source snapshot.
#
# Usage:
#   bash scripts/release.sh --version v0.3.0
#   bash scripts/release.sh --version v0.3.0 --notes RELEASE_NOTES.md --yes
#
# Flags:
#   --version TAG   Release tag, required (e.g. v0.3.0)
#   --notes FILE    Release notes file (passed to gh release create)
#   --base BRANCH   Base branch (default: main)
#   --yes           Push the tag and create the GitHub Release
#   --skip-ci       Skip the local CI gate (not recommended)
#   --help          Show this help
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

VERSION=""
NOTES=""
BASE="main"
ASSUME_YES=0
SKIP_CI=0

usage() {
    sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

die() {
    echo "release: $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            [[ $# -ge 2 ]] || die "--version needs a tag"
            VERSION="$2"; shift 2 ;;
        --notes)
            [[ $# -ge 2 ]] || die "--notes needs a file"
            NOTES="$2"; shift 2 ;;
        --base)
            [[ $# -ge 2 ]] || die "--base needs a branch"
            BASE="$2"; shift 2 ;;
        --yes)
            ASSUME_YES=1; shift ;;
        --skip-ci)
            SKIP_CI=1; shift ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            die "unknown argument: $1 (use --help)" ;;
    esac
done

[[ -n "$VERSION" ]] || { usage; exit 2; }
[[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-+].+)?$ ]] \
    || die "version must look like v1.2.3 (got: $VERSION)"
[[ -z "$NOTES" || -f "$NOTES" ]] || die "notes file not found: $NOTES"

command -v git >/dev/null 2>&1 || die "git not found"
if [[ "$ASSUME_YES" == "1" ]]; then
    command -v gh >/dev/null 2>&1 || die "gh not found"
    gh auth status >/dev/null 2>&1 || die "gh is not authenticated"
fi

git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || die "not a git worktree"

if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    die "working tree is dirty; commit or stash changes first"
fi
CURRENT_BRANCH="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
[[ "$CURRENT_BRANCH" == "$BASE" ]] \
    || die "must be on $BASE (currently $CURRENT_BRANCH)"

git -C "$ROOT_DIR" fetch origin "$BASE" >/dev/null 2>&1 \
    || die "git fetch origin $BASE failed"
if [[ "$(git -C "$ROOT_DIR" rev-list --count "HEAD..origin/$BASE")" != "0" ]]; then
    die "local $BASE is behind origin/$BASE; pull first"
fi
if git -C "$ROOT_DIR" rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
    die "tag already exists: $VERSION"
fi

if [[ "$SKIP_CI" == "0" ]]; then
    echo "release: running local CI gate"
    bash "$SCRIPT_DIR/ci.sh" || die "CI gate failed; release aborted"
else
    echo "release: WARNING: CI gate skipped"
fi

echo "release: creating annotated tag $VERSION"
git -C "$ROOT_DIR" tag -a "$VERSION" -m "Release $VERSION" \
    || die "git tag failed"

if [[ "$ASSUME_YES" == "0" ]]; then
    cat <<EOF
release: tag created locally; nothing pushed

Next steps:
  git -C "$ROOT_DIR" push origin $VERSION
  gh release create $VERSION --generate-notes
EOF
    exit 0
fi

echo "release: pushing tag $VERSION"
git -C "$ROOT_DIR" push origin "$VERSION" || die "git push tag failed"

echo "release: creating GitHub Release"
if [[ -n "$NOTES" ]]; then
    gh release create "$VERSION" --title "$VERSION" --notes-file "$NOTES"
else
    gh release create "$VERSION" --title "$VERSION" --generate-notes
fi || die "gh release create failed"

echo "release: done: $VERSION"
