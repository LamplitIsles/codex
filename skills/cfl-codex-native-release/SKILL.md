---
name: cfl-codex-native-release
description: Build CFL-maintained Codex app-server archives from the fork's release branch for Linux x64 musl or macOS ARM64, then hand them to CFL's local native npm publisher. Use for CFL native builds, not upstream Codex releases or npm publication.
---

# CFL Codex native release

`cfl/local-install` is CFL's native-artifact release source. It is deliberately
published from that branch rather than merged into upstream `main`; do not open
or merge a PR as a substitute for the release workflow.

This repository owns the native app-server build and local archive. The sibling
`codex-for-love` repository owns the scoped npm packages and their local
publication wizard. Never publish upstream `@openai/codex` from this fork.

## Prepare the exact source

Read this repository's `AGENTS.md`, then inspect the CFL package identity
contracts in `../codex-for-love/release/` before building. Confirm the branch,
source revision, intended provenance release label, target, supported Codex
version, output naming, and clean worktree. Push release commits to the source
branch with `og`; do not merge the branch.

Use the shared CFL cargo cache and preserve the known low-memory release
profile. Inspect Cargo freshness before a heavy build and stop on an unexpected
wide rebuild. On Linux, prove the required systemd resource scope before the
musl build and run only one heavy build at once.

## Build by native host

- Linux x64: use `scripts/cfl_release.py` and its prerequisite/assembly checks
  for `x86_64-unknown-linux-musl`. It packages `codex-app-server` together with
  the exact same-version official code-mode helper.
- macOS ARM64: on the release checkout, run
  `bash skills/cfl-codex-native-release/scripts/build-darwin-arm64.sh <cfl-release-tag>`.
  It requires Homebrew Python at `/opt/homebrew/bin/python3`, reuses the
  matching official code-mode helper, and writes a self-describing archive
  under `.scratch/`. Do not cross-package a Linux executable or claim Intel
  macOS support from an ARM build.

For either platform, validate archive layout, executable hashes, target and
runtime metadata before handoff. Keep the artifact's source revision and
provenance release label available for CFL's native package provenance.

## Release and handoff

Do not create a fork GitHub Release or Git tag for this path. Hand the verified
local archive, SHA-256 value, source revision, provenance release label, target,
and helper version to the CFL release workflow. It copies both archives into
`.scratch/native-release-<version>/` and runs its local native npm wizard.

The follow-up native npm package is an independent CFL-repository operation:
it may only package these verified bytes and must be published before a CFL main
package pins it.
