# CFL native release source

`cfl/local-install` carries CFL's app-server and local compaction changes on
upstream `rust-v0.156.1` (peeled commit
`b412ff32c417f855c2b2d1581b77058eed87c84b`). This branch produces
Linux x64 musl and macOS ARM64 archives for the CFL scoped npm packages; it
does not publish upstream `@openai/codex` or deploy a Partner.

Use `skills/cfl-codex-native-release/SKILL.md` for the current build and
handoff sequence. Both hosts must build the same reviewed source revision and
package the `codex-code-mode-host` from the official Codex **0.156.1** package
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
