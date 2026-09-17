---
name: cfl-codex-native-release
description: Build and release the CFL-maintained Codex app-server artifacts from the fork's release branch for Linux x64 musl or macOS ARM64. Use for CFL native artifact releases, not upstream Codex releases or npm publication.
---

# CFL Codex native release

`cfl/local-install` is CFL's native-artifact release source. It is deliberately
published from that branch rather than merged into upstream `main`; do not open
or merge a PR as a substitute for the release workflow.

This repository owns the native app-server artifact and the fork GitHub Release.
The sibling `codex-for-love` repository owns the scoped npm packages, their
provenance contracts, and main-package publication. Never publish upstream
`@openai/codex` from this fork.

## Prepare the exact source

Read this repository's `AGENTS.md`, then inspect the CFL package identity
contracts in `../codex-for-love/release/` before building. Confirm the branch,
source revision, intended `cfl/...` release tag, target, supported Codex
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
- macOS ARM64: build natively on an ARM Mac with the same release profile and
  shared cache convention, omitting the Linux target. Reuse the matching
  official code-mode helper; do not cross-package a Linux executable or claim
  Intel macOS support from an ARM build.

For either platform, validate archive layout, executable hashes, target and
runtime metadata before uploading. Keep the artifact's source revision and
`cfl/...` tag available for CFL's native package provenance.

## Release and handoff

After explicit authorization for the external release, use `gh` only for the
fork GitHub Release/tag asset operation, as allowed by repository policy.
Verify the uploaded asset digest and release/tag identity. Hand the exact asset
URL, SHA-256 values, source revision, release tag, target, and helper version to
the CFL release workflow.

The follow-up native npm package is an independent CFL-repository operation:
it may only package these verified bytes and must be published before a CFL main
package pins it. A GitHub Release alone does not authorize deployment or npm
publication.
