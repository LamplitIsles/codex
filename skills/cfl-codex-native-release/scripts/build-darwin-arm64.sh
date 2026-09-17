#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <cfl-release-tag>" >&2
  exit 64
fi

release_tag=$1
repo_root=$(cd "$(dirname "$0")/../../.." && pwd)
git_bin=/opt/homebrew/bin/git
python_bin=/opt/homebrew/bin/python3
helper_root="$HOME/.cache/lamplitisles/codex-for-love/mac-native-beta-staging/source/node_modules/.pnpm"
helper_pattern='*/@openai+codex@0.154.0-darwin-arm64/node_modules/@openai/codex/vendor/aarch64-apple-darwin/bin/codex-code-mode-host'

test -x "$git_bin"
test -x "$python_bin"
cd "$repo_root"
test "$("$git_bin" rev-parse --abbrev-ref HEAD)" = "cfl/local-install"
test -z "$("$git_bin" status --porcelain)"

helper=$(find "$helper_root" -type f -path "$helper_pattern" -print -quit)
test -n "$helper"
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
