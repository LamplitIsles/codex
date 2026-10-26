#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <cfl-release-tag> <official-code-mode-host-bin>" >&2
  exit 64
fi

release_tag=$1
helper=$2
repo_root=$(cd "$(dirname "$0")/../../.." && pwd)
git_bin=/opt/homebrew/bin/git
python_bin=/opt/homebrew/bin/python3

test -x "$git_bin"
test -x "$python_bin"
cd "$repo_root"
case "$("$git_bin" rev-parse --abbrev-ref HEAD)" in
  cfl/local-install|cfl/0.164-native) ;;
  *) echo "build requires the CFL release or reviewed 0.164 branch" >&2; exit 1 ;;
esac
"$git_bin" merge-base --is-ancestor 880185c212186edc3211c02eb36c7dd7584917f7 HEAD
test -z "$("$git_bin" status --porcelain)"

test -x "$helper"

mkdir -p .scratch
release_dir=$(mktemp -d "$PWD/.scratch/cfl-darwin.XXXXXX")

/usr/sbin/taskpolicy -m 6144 -P kill \
  "$python_bin" scripts/cfl_release.py \
  --target aarch64-apple-darwin \
  --release-tag "$release_tag" \
  --code-mode-host-bin "$helper" \
  --output-dir "$release_dir" \
  --jobs 4

archive=$(find "$release_dir" -maxdepth 1 -type f -name '*.tar.gz' -print -quit)
test -n "$archive"
shasum -a 256 "$archive"
tar -tzf "$archive"
provenance_path=$(tar -tzf "$archive" | awk '/\/provenance\.json$/ { print; exit }')
test -n "$provenance_path"
tar -xOzf "$archive" "$provenance_path"
printf 'archive=%s\n' "$archive"
