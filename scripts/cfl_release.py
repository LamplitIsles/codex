#!/usr/bin/env python3
"""Build a CFL Codex release archive from this exact checkout."""

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path


SUPPORTED_TARGETS = {
    "x86_64-unknown-linux-gnu",
    "aarch64-apple-darwin",
}
REPO_ROOT = Path(__file__).resolve().parents[1]


def default_target_dir() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_home / "lamplitisles" / "codex-for-love" / "cargo-target"


def positive_jobs(value: str) -> int:
    jobs = int(value)
    if jobs < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return jobs


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def executable(path: Path, description: str) -> Path:
    path = path.resolve()
    if not path.is_file() or not path.stat().st_mode & stat.S_IXUSR:
        raise RuntimeError(f"{description} must be an executable file: {path}")
    return path


def source_revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def codex_version() -> str:
    for line in (REPO_ROOT / "codex-rs" / "Cargo.toml").read_text().splitlines():
        if line.startswith("version = "):
            return line.split('"')[1]
    raise RuntimeError("workspace version is missing from codex-rs/Cargo.toml")


def rust_host_triple() -> str:
    output = subprocess.check_output(["rustc", "-vV"], text=True)
    for line in output.splitlines():
        if line.startswith("host: "):
            return line.removeprefix("host: ")
    raise RuntimeError("rustc -vV did not report a host triple")


def build_codex(target: str, target_dir: Path, jobs: int) -> Path:
    host = rust_host_triple()
    if target != host:
        raise RuntimeError(
            f"target {target} does not match native rustc host {host}; cross-compilation is unsupported"
        )
    environment = os.environ | {
        "CARGO_BUILD_JOBS": str(jobs),
        "CARGO_TARGET_DIR": str(target_dir),
    }
    subprocess.check_call(
        [
            "cargo",
            "build",
            "--locked",
            "--release",
            "--jobs",
            str(jobs),
            "--package",
            "codex-cli",
            "--bin",
            "codex",
        ],
        cwd=REPO_ROOT / "codex-rs",
        env=environment,
    )
    return target_dir / "release" / "codex"


def archive_name(release_tag: str, target: str) -> str:
    return f"cfl-codex-{release_tag.replace('/', '-')}-{target}.tar.gz"


def write_archive(
    output_dir: Path,
    release_tag: str,
    target: str,
    codex_bin: Path,
    helper_bin: Path,
) -> Path:
    revision = source_revision()
    version = codex_version()
    root_name = archive_name(release_tag, target).removesuffix(".tar.gz")
    archive_path = output_dir / archive_name(release_tag, target)
    provenance = {
        "schemaVersion": 1,
        "forkRepository": "https://github.com/lamplitisles/codex",
        "sourceRevision": revision,
        "releaseTag": release_tag,
        "codexVersion": version,
        "target": target,
        "executables": {
            "bin/codex": sha256(codex_bin),
            "bin/codex-code-mode-host": sha256(helper_bin),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        raise RuntimeError(f"release archive already exists: {archive_path}")
    with tarfile.open(archive_path, "w:gz") as archive:
        for source, relative in (
            (codex_bin, "bin/codex"),
            (helper_bin, "bin/codex-code-mode-host"),
            (REPO_ROOT / "LICENSE", "LICENSE"),
            (REPO_ROOT / "NOTICE", "NOTICE"),
        ):
            archive.add(source, arcname=f"{root_name}/{relative}", recursive=False)
        encoded = (json.dumps(provenance, indent=2) + "\n").encode()
        info = tarfile.TarInfo(f"{root_name}/provenance.json")
        info.size = len(encoded)
        info.mode = 0o644
        archive.addfile(info, fileobj=io.BytesIO(encoded))
    return archive_path


def write_manifest(output_dir: Path) -> Path:
    archives = sorted(output_dir.glob("cfl-codex-*.tar.gz"))
    if len(archives) != len(SUPPORTED_TARGETS):
        raise RuntimeError(
            "checksum finalization requires exactly one archive for each supported target"
        )
    targets = {
        target
        for target in SUPPORTED_TARGETS
        if any(archive.name.endswith(f"-{target}.tar.gz") for archive in archives)
    }
    if targets != SUPPORTED_TARGETS:
        raise RuntimeError(
            "checksum finalization requires exactly one archive for each supported target"
        )
    manifest = output_dir / "SHA256SUMS"
    manifest.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in archives))
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(SUPPORTED_TARGETS))
    parser.add_argument("--release-tag")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--code-mode-host-bin", type=Path)
    parser.add_argument("--codex-bin", type=Path)
    parser.add_argument("--cargo-target-dir", type=Path)
    parser.add_argument(
        "--jobs",
        type=positive_jobs,
        default=positive_jobs(os.environ.get("CARGO_BUILD_JOBS", "4")),
        help="Cargo jobs (default: %(default)s; run only one native build at a time)",
    )
    parser.add_argument(
        "--finalize-checksums",
        action="store_true",
        help="write SHA256SUMS only after verifying a clean two-target output directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.finalize_checksums:
        if any(
            value is not None
            for value in (args.target, args.codex_bin, args.code_mode_host_bin)
        ):
            raise RuntimeError("--finalize-checksums takes only --output-dir")
        manifest = write_manifest(args.output_dir.resolve())
        print(f"checksums: {manifest}")
        return 0
    if (
        args.target is None
        or args.release_tag is None
        or args.code_mode_host_bin is None
    ):
        raise RuntimeError(
            "--target, --release-tag, and --code-mode-host-bin are required to build an archive"
        )
    helper = executable(args.code_mode_host_bin, "code-mode host")
    if args.codex_bin is not None:
        codex = executable(args.codex_bin, "Codex")
    else:
        target_dir = args.cargo_target_dir or default_target_dir()
        codex = executable(
            build_codex(args.target, target_dir, args.jobs), "built Codex"
        )
    archive = write_archive(
        args.output_dir.resolve(), args.release_tag, args.target, codex, helper
    )
    print(f"archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
