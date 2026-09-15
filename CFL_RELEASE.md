# CFL 0.154 release maintenance

`cfl/0.154` is maintained from upstream `rust-v0.154.0` peeled commit
`6b9826e3aa83b1a5947db50f4332cb9c65f1b340`. The current release produces
only static Linux x64 (`x86_64-unknown-linux-musl`). Windows, macOS, other
targets, model calls, deployment, and automated publication are deliberately
outside this release path.

Do not publish a release from this branch. Build the forked
`codex-app-server` binary from source with the matching official musl
0.154.0 `codex-code-mode-host`; `--code-mode-host-bin` names that helper.

On Linux, keep Cargo artifacts outside the checkout so CFL's existing cache is
reused. Release compilation defaults to four Cargo jobs. Do not run it while
another release build is active; use `--jobs N` only for an explicit override.
The command invokes Cargo with the explicit musl target so it reuses the shared
`x86_64-unknown-linux-musl/release/` cache seam. It preserves the established
low-memory release profile:
`CARGO_INCREMENTAL=0`, `CARGO_PROFILE_RELEASE_INCREMENTAL=false`,
`CARGO_PROFILE_RELEASE_LTO=false`, `CARGO_PROFILE_RELEASE_DEBUG=0`,
`CARGO_PROFILE_RELEASE_STRIP=symbols`, `CARGO_PROFILE_RELEASE_OPT_LEVEL=1`,
and `CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16`. Before Linux Cargo starts, the
entry point verifies a systemd user scope that enforces `MemoryMax=6G`,
`MemorySwapMax=512M`, `CPUQuota=800%`, and `TasksMax=256`; it aborts when those
limits are unavailable. The Linux cache was built by the explicit host Rust
and Cargo binaries, so do not run its Cargo command from a Nix development
shell. The entry point uses the target-specific musl gcc/g++ linker and
isolates pkg-config from GNU OpenSSL paths; it verifies those prerequisites in
the same resource-limited unit before Cargo starts.

```shell
python3 scripts/cfl_release.py \
  --target x86_64-unknown-linux-musl --release-tag cfl/v0.154.0-rc.1 \
  --output-dir /tmp/cfl-codex-release \
  --cargo-target-dir "${XDG_CACHE_HOME:-$HOME/.cache}/lamplitisles/codex-for-love/cargo-target" \
  --code-mode-host-bin /path/to/official/codex-code-mode-host
```

Each `tar.gz` contains `bin/codex-app-server`, `bin/codex-code-mode-host`, `LICENSE`,
`NOTICE`, and `provenance.json`. After the Linux build has placed its one
archive in a clean output directory, generate the manifest with
`python3 scripts/cfl_release.py --output-dir /tmp/cfl-codex-release --finalize-checksums`.
Finalization fails unless the directory has exactly one archive for the
supported target, so stale or incomplete output cannot be published.
Provenance identifies the fork, source
revision, release tag, Codex version, target, and SHA-256 digest of each
executable; it contains no build-host paths. `SHA256SUMS` is regenerated in the
shared output directory and must list the one Linux archive. Verify it with
`sha256sum --check SHA256SUMS`, inspect the provenance file, and run
`bin/codex-app-server --version` plus `bin/codex-code-mode-host --help` from a
temporary extraction. A later, separately authorized release step may upload
the archive and `SHA256SUMS`.
