# CFL native release source

`cfl/local-install` carries CFL's app-server and local compaction changes on
upstream `rust-v0.164.0` (peeled commit
`6aaac694803004a63c6f393d153c96d22521a6b9`). This branch produces
Linux x64 musl and macOS ARM64 archives for the CFL scoped npm packages; it
does not publish upstream `@openai/codex` or deploy a Partner.

Use `skills/cfl-codex-native-release/SKILL.md` for the current build and
handoff sequence. Both hosts must build the same reviewed source revision and
package the `codex-code-mode-host` from the official Codex **0.164.0** package
for their own target. `scripts/cfl_release.py` records source revision, target,
version, release label, and executable hashes in each archive. The sibling
`codex-for-love/skills/cfl-release/SKILL.md` owns native npm packaging,
publication, and installed-artifact checks.

Keep the shared Cargo cache and low-memory profile described in `AGENTS.md`.
On Linux, the release entry point verifies an enforced systemd resource scope
and the musl toolchain before compiling. On macOS, use the ARM host and
`build-darwin-arm64.sh`. After both archives are verified, copy them into one
clean output directory and run `scripts/cfl_release.py --output-dir <dir>
--finalize-checksums` to produce `SHA256SUMS` for the two-target handoff.

Spec #4668 recovers release base `880185c212186edc3211c02eb36c7dd7584917f7`
without rewriting its history. The upgrade PR targets `cfl/local-install`;
`cfl/0.164-native` is the build candidate. Proposed downstream native npm
version is **0.7.0**, with provenance label `cfl/v0.164.0-native.0.7.0`
(no Git tag). The downstream publisher must check version availability.

Owned runtime delta: explicit local compaction routing and Owner prompt,
current-turn-only retention, neutral continuity prefix and checkpoint reuse.
The override uses 0.164.0 local compaction step/world-state handling and
disables speculative remote compaction. Upstream lockfile and all unrelated
source remain exactly stable 0.164.0; prior lockfile version normalization is
obsolete because this stable release already records workspace 0.164.0.
