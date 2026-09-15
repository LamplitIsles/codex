# CFL 0.154 release maintenance

`cfl/0.154` is maintained from upstream `rust-v0.154.0` peeled commit
`6b9826e3aa83b1a5947db50f4332cb9c65f1b340`. It produces only Linux x64
(`x86_64-unknown-linux-gnu`) and Apple Silicon macOS
(`aarch64-apple-darwin`). Windows, other targets, model calls, deployment, and
automated publication are deliberately outside this release path.

After the reviewed PR merges, tag that merge and create one GitHub release. Do
not publish a release from an unmerged branch. Build each target from the same
tagged checkout with the matching official 0.154.0 `codex-code-mode-host`
installed by the official Codex package. The command builds the forked `codex`
binary from source; `--code-mode-host-bin` names that official helper.

On Linux, keep Cargo artifacts outside the checkout so CFL's existing cache is
reused:

```shell
python3 scripts/cfl_release.py \
  --target x86_64-unknown-linux-gnu --release-tag cfl/v0.154.0-rc.1 \
  --output-dir /tmp/cfl-codex-release \
  --cargo-target-dir "${XDG_CACHE_HOME:-$HOME/.cache}/lamplitisles/codex-for-love/cargo-target" \
  --code-mode-host-bin /path/to/official/codex-code-mode-host
```

On the authorized Apple Silicon Mac, clone or check out the exact same tagged
source and use a persistent Mac-local cache:

```shell
python3 scripts/cfl_release.py \
  --target aarch64-apple-darwin --release-tag cfl/v0.154.0-rc.1 \
  --output-dir /tmp/cfl-codex-release \
  --cargo-target-dir "${XDG_CACHE_HOME:-$HOME/.cache}/lamplitisles/codex-for-love/cargo-target" \
  --code-mode-host-bin /path/to/official/codex-code-mode-host
```

Each `tar.gz` contains `bin/codex`, `bin/codex-code-mode-host`, `LICENSE`,
`NOTICE`, and `provenance.json`. After both host builds have placed their
archives in one clean output directory, generate the manifest with
`python3 scripts/cfl_release.py --output-dir /tmp/cfl-codex-release --finalize-checksums`.
Finalization fails unless the directory has exactly one archive for each
supported target, so stale or incomplete output cannot be published.
Provenance identifies the fork, source
revision, release tag, Codex version, target, and SHA-256 digest of each
executable; it contains no build-host paths. `SHA256SUMS` is regenerated in the
shared output directory and must list both archives. Verify it with
`sha256sum --check SHA256SUMS` on Linux (or `shasum -a 256 -c SHA256SUMS` on
macOS), inspect the two provenance files, and run `bin/codex --version` plus
`bin/codex-code-mode-host --help` from temporary extractions. Upload exactly
the two archives and `SHA256SUMS` to the post-merge GitHub release.
