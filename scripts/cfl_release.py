#!/usr/bin/env python3
"""Build a CFL Codex release archive from this exact checkout."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


SUPPORTED_TARGETS = {
    "x86_64-unknown-linux-musl",
    "aarch64-apple-darwin",
}
LINUX_MUSL_TARGET = "x86_64-unknown-linux-musl"
REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_PROFILE_ENV = {
    "CARGO_INCREMENTAL": "0",
    "CARGO_PROFILE_RELEASE_INCREMENTAL": "false",
    "CARGO_PROFILE_RELEASE_LTO": "false",
    "CARGO_PROFILE_RELEASE_DEBUG": "0",
    "CARGO_PROFILE_RELEASE_STRIP": "symbols",
    "CARGO_PROFILE_RELEASE_OPT_LEVEL": "1",
    "CARGO_PROFILE_RELEASE_CODEGEN_UNITS": "16",
}
LINUX_SCOPE_PROPERTIES = {
    "MemoryMax": "6G",
    "MemorySwapMax": "512M",
    "CPUQuota": "800%",
    "TasksMax": "256",
}
LINUX_SCOPE_EXPECTED = {
    "MemoryMax": "6442450944",
    "MemorySwapMax": "536870912",
    "CPUQuotaPerSecUSec": "8s",
    "TasksMax": "256",
}
LINUX_HOST_TOOLCHAIN = Path("/run/current-system/sw/bin")
LINUX_MUSL_ENV = {
    "CC": "/run/current-system/sw/bin/x86_64-unknown-linux-musl-gcc",
    "CXX": "/run/current-system/sw/bin/x86_64-unknown-linux-musl-g++",
    "CFLAGS": "-pthread",
    "CXXFLAGS": "-pthread",
    "PKG_CONFIG": "/run/current-system/sw/bin/pkg-config",
    "PKG_CONFIG_ALLOW_CROSS": "1",
    "PKG_CONFIG_LIBDIR": "/nonexistent",
    "PKG_CONFIG_PATH": "/nonexistent",
    "AWS_LC_SYS_NO_JITTER_ENTROPY": "1",
}


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


def host_executable(name: str) -> str:
    if sys.platform == "linux":
        path = LINUX_HOST_TOOLCHAIN / name
        if not path.is_file() or not path.stat().st_mode & stat.S_IXUSR:
            raise RuntimeError(f"Linux release requires host {name}: {path}")
        return str(path)
    return shutil.which(name) or name


def rust_host_triple() -> str:
    output = subprocess.check_output([host_executable("rustc"), "-vV"], text=True)
    for line in output.splitlines():
        if line.startswith("host: "):
            return line.removeprefix("host: ")
    raise RuntimeError("rustc -vV did not report a host triple")


def release_environment(target: str, target_dir: Path, jobs: int) -> dict[str, str]:
    environment = (
        os.environ
        | RELEASE_PROFILE_ENV
        | {
            "CARGO_BUILD_JOBS": str(jobs),
            "CARGO_TARGET_DIR": str(target_dir),
        }
    )
    if sys.platform == "linux":
        for name in tuple(environment):
            if name.startswith(("OPENSSL_", "PKG_CONFIG_")) or name in {
                "CC",
                "CXX",
                "CFLAGS",
                "CXXFLAGS",
            }:
                environment.pop(name)
        environment |= {
            "RUSTC": host_executable("rustc"),
        }
        if target == LINUX_MUSL_TARGET:
            environment |= LINUX_MUSL_ENV
            environment["CMAKE_BUILD_PARALLEL_LEVEL"] = str(jobs)
            environment["MAKEFLAGS"] = f"-j{jobs}"
            target_variable = target.upper().replace("-", "_")
            environment[f"CC_{target_variable}"] = environment["CC"]
            environment[f"CXX_{target_variable}"] = environment["CXX"]
            environment[f"CARGO_TARGET_{target_variable}_LINKER"] = environment["CC"]
            environment[f"PKG_CONFIG_LIBDIR_{target_variable}"] = "/nonexistent"
            environment[f"PKG_CONFIG_PATH_{target_variable}"] = "/nonexistent"
            environment[f"AWS_LC_SYS_NO_JITTER_ENTROPY_{target_variable}"] = "1"
    return environment


def verify_linux_scope() -> None:
    """Prove that systemd accepts and enforces the release limits before Cargo runs."""
    systemd_run = shutil.which("systemd-run")
    systemctl = shutil.which("systemctl")
    sleep = shutil.which("sleep")
    if systemd_run is None or systemctl is None or sleep is None:
        raise RuntimeError(
            "Linux release scope requires systemd-run, systemctl, and sleep"
        )
    unit = f"cfl-codex-release-probe-{os.getpid()}"
    scope = f"{unit}.scope"
    properties = [
        f"--property={name}={value}" for name, value in LINUX_SCOPE_PROPERTIES.items()
    ]
    runner = subprocess.Popen(
        [systemd_run, "--user", "--scope", f"--unit={unit}", *properties, sleep, "30"],
        stdout=subprocess.DEVNULL,
    )
    try:
        for _ in range(30):
            result = subprocess.run(
                [
                    systemctl,
                    "--user",
                    "show",
                    scope,
                    "--property=MemoryMax",
                    "--property=MemorySwapMax",
                    "--property=CPUQuotaPerSecUSec",
                    "--property=TasksMax",
                    "--property=LoadState",
                    "--property=ActiveState",
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
            )
            if (
                result.returncode == 0
                and "LoadState=loaded" in result.stdout
                and "ActiveState=active" in result.stdout
            ):
                output = result.stdout
                break
            if runner.poll() is not None:
                raise RuntimeError(
                    "Linux release scope stopped before its limits could be verified"
                )
            time.sleep(0.1)
        else:
            raise RuntimeError(
                "Linux release scope did not become available for verification"
            )
        actual = dict(line.split("=", maxsplit=1) for line in output.splitlines())
        limits = {key: actual[key] for key in LINUX_SCOPE_EXPECTED}
        if limits != LINUX_SCOPE_EXPECTED:
            raise RuntimeError(
                f"Linux release scope limits were not enforced: {limits}; "
                f"expected {LINUX_SCOPE_EXPECTED}"
            )
    finally:
        subprocess.run([systemctl, "--user", "stop", scope], check=False)
        runner.wait()


def linux_scoped(
    command: list[str],
    environment: dict[str, str],
    working_directory: Path | None = None,
) -> list[str]:
    systemd_run = shutil.which("systemd-run")
    if systemd_run is None:
        raise RuntimeError("Linux release scope requires systemd-run")
    properties = [
        f"--property={name}={value}" for name, value in LINUX_SCOPE_PROPERTIES.items()
    ]
    scoped_environment = [
        f"--setenv={name}={environment[name]}"
        for name in (
            "PATH",
            "CARGO_HOME",
            "CARGO_TARGET_DIR",
            "CARGO_BUILD_JOBS",
            "CARGO_INCREMENTAL",
            "CARGO_PROFILE_RELEASE_INCREMENTAL",
            "CARGO_PROFILE_RELEASE_LTO",
            "CARGO_PROFILE_RELEASE_DEBUG",
            "CARGO_PROFILE_RELEASE_STRIP",
            "CARGO_PROFILE_RELEASE_OPT_LEVEL",
            "CARGO_PROFILE_RELEASE_CODEGEN_UNITS",
            "CARGO_ENCODED_RUSTFLAGS",
            "RUSTFLAGS",
            "RUSTC",
            "RUSTDOC",
            "CARGO_LOG",
            "PKG_CONFIG",
            "PKG_CONFIG_PATH",
            "PKG_CONFIG_ALLOW_CROSS",
            "PKG_CONFIG_LIBDIR",
            "LIBCLANG_PATH",
            "LD_LIBRARY_PATH",
            "CC",
            "CXX",
            "CFLAGS",
            "CXXFLAGS",
            "CMAKE_BUILD_PARALLEL_LEVEL",
            "MAKEFLAGS",
            "AWS_LC_SYS_NO_JITTER_ENTROPY",
            "CC_X86_64_UNKNOWN_LINUX_MUSL",
            "CXX_X86_64_UNKNOWN_LINUX_MUSL",
            "CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER",
            "PKG_CONFIG_LIBDIR_X86_64_UNKNOWN_LINUX_MUSL",
            "PKG_CONFIG_PATH_X86_64_UNKNOWN_LINUX_MUSL",
            "AWS_LC_SYS_NO_JITTER_ENTROPY_X86_64_UNKNOWN_LINUX_MUSL",
        )
        if name in environment
    ]
    scoped_command = [
        systemd_run,
        "--user",
        "--wait",
        "--collect",
        "--pipe",
        "--unit=cfl-codex-app-server-release",
        "--property=RuntimeMaxSec=60min",
        *properties,
        *scoped_environment,
    ]
    if working_directory is not None:
        scoped_command.append(f"--working-directory={working_directory}")
    return [*scoped_command, *command]


def linux_musl_preflight_command(workspace: Path) -> list[str]:
    """Validate the isolated musl compiler and linker in the release scope."""
    return [
        host_executable("bash"),
        "-c",
        """
            set -eu
            cargo_bin="$1"
            expected_workspace="$2"
            test "$PWD" = "$expected_workspace"
            test -f Cargo.toml
            "$RUSTC" -vV | grep -Fqx 'rustc 1.97.1 (8bab26f4f 2026-07-14)'
            "$RUSTC" -vV | grep -Fqx 'commit-hash: 8bab26f4f68e0e26f0bb7960be334d5b520ea452'
            "$RUSTC" -vV | grep -Fqx 'LLVM version: 22.1.6'
            "$cargo_bin" -V | grep -Fqx 'cargo 1.97.1 (c980f4866 2026-06-30)'
            set -- "$("$RUSTC" --print target-libdir --target x86_64-unknown-linux-musl)"/libstd-*.rlib
            test -f "$1"
            "$CC" --version >/dev/null
            "$CXX" --version >/dev/null
            "$PKG_CONFIG" --version >/dev/null
            probe="$(mktemp)"
            trap 'rm -f "$probe"' EXIT
            printf '#include <stddef.h>\\n#include <limits.h>\\n#include <stdio.h>\\nint main(void) { return 0; }\\n' |
                "$CC" -static -x c - -o "$probe"
            ! readelf -lW "$probe" | grep -Fq 'Requesting program interpreter'
            ! readelf -dW "$probe" | grep -Fq '(NEEDED)'
        """,
        "cfl-codex-app-server-musl-preflight",
        host_executable("cargo"),
        str(workspace),
    ]


def preflight_linux_musl(target_dir: Path, jobs: int) -> None:
    environment = release_environment(LINUX_MUSL_TARGET, target_dir, jobs)
    workspace = REPO_ROOT / "codex-rs"
    verify_linux_scope()
    command = linux_scoped(
        linux_musl_preflight_command(workspace), environment, workspace
    )
    subprocess.check_call(command, cwd=workspace, env=environment)


def build_app_server(target: str, target_dir: Path, jobs: int) -> Path:
    if target != LINUX_MUSL_TARGET:
        host = rust_host_triple()
        if target != host:
            raise RuntimeError(
                f"target {target} does not match native rustc host {host}; cross-compilation is unsupported"
            )
        environment = release_environment(target, target_dir, jobs)
        workspace = REPO_ROOT / "codex-rs"
        command = [
            host_executable("cargo"),
            "build",
            "--locked",
            "--release",
            "--jobs",
            str(jobs),
            "--package",
            "codex-app-server",
            "--bin",
            "codex-app-server",
        ]
        subprocess.check_call(command, cwd=workspace, env=environment)
        return target_dir / "release" / "codex-app-server"

    environment = release_environment(target, target_dir, jobs)
    workspace = REPO_ROOT / "codex-rs"
    verify_linux_scope()
    command = [
        host_executable("cargo"),
        "build",
        "--locked",
        "--release",
        "--target",
        target,
        "--jobs",
        str(jobs),
        "--package",
        "codex-app-server",
        "--bin",
        "codex-app-server",
    ]
    command = linux_scoped(command, environment, workspace)
    subprocess.check_call(command, cwd=workspace, env=environment)
    return target_dir / target / "release" / "codex-app-server"


def archive_name(release_tag: str, target: str) -> str:
    return f"cfl-codex-app-server-{release_tag.replace('/', '-')}-{target}.tar.gz"


def archive_binary(app_server_bin: Path, directory: Path) -> Path:
    """Copy the verified Cargo artifact without modifying the cache entry."""
    artifact = directory / "codex-app-server"
    shutil.copy2(app_server_bin, artifact)
    return artifact


def write_archive(
    output_dir: Path,
    release_tag: str,
    target: str,
    app_server_bin: Path,
    helper_bin: Path,
) -> Path:
    revision = source_revision()
    version = codex_version()
    root_name = archive_name(release_tag, target).removesuffix(".tar.gz")
    archive_path = output_dir / archive_name(release_tag, target)
    output_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        raise RuntimeError(f"release archive already exists: {archive_path}")
    with tempfile.TemporaryDirectory() as temporary:
        artifact = archive_binary(app_server_bin, Path(temporary))
        provenance = {
            "schemaVersion": 1,
            "forkRepository": "https://github.com/lamplitisles/codex",
            "sourceRevision": revision,
            "releaseTag": release_tag,
            "codexVersion": version,
            "target": target,
            "executables": {
                "bin/codex-app-server": sha256(artifact),
                "bin/codex-code-mode-host": sha256(helper_bin),
            },
        }
        with tarfile.open(archive_path, "w:gz") as archive:
            for source, relative in (
                (artifact, "bin/codex-app-server"),
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
    archives = sorted(output_dir.glob("cfl-codex-app-server-*.tar.gz"))
    if len(archives) != len(SUPPORTED_TARGETS):
        raise RuntimeError(
            "checksum finalization requires exactly one archive for the supported target"
        )
    targets = {
        target
        for target in SUPPORTED_TARGETS
        if any(archive.name.endswith(f"-{target}.tar.gz") for archive in archives)
    }
    if targets != SUPPORTED_TARGETS:
        raise RuntimeError(
            "checksum finalization requires exactly one archive for the supported target"
        )
    manifest = output_dir / "SHA256SUMS"
    manifest.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in archives))
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(SUPPORTED_TARGETS))
    parser.add_argument("--release-tag")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--code-mode-host-bin", type=Path)
    parser.add_argument("--app-server-bin", type=Path)
    parser.add_argument("--cargo-target-dir", type=Path)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="verify Linux musl prerequisites in the enforced scope without running Cargo",
    )
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
    if args.preflight_only:
        if args.target != LINUX_MUSL_TARGET or args.release_tag is not None:
            raise RuntimeError(
                "--preflight-only requires only --target x86_64-unknown-linux-musl"
            )
        target_dir = args.cargo_target_dir or default_target_dir()
        preflight_linux_musl(target_dir, args.jobs)
        print("musl preflight: ready")
        return 0
    if args.finalize_checksums:
        if args.output_dir is None:
            raise RuntimeError("--finalize-checksums requires --output-dir")
        if any(
            value is not None
            for value in (args.target, args.app_server_bin, args.code_mode_host_bin)
        ):
            raise RuntimeError("--finalize-checksums takes only --output-dir")
        manifest = write_manifest(args.output_dir.resolve())
        print(f"checksums: {manifest}")
        return 0
    if (
        args.target is None
        or args.release_tag is None
        or args.code_mode_host_bin is None
        or args.output_dir is None
    ):
        raise RuntimeError(
            "--target, --release-tag, and --code-mode-host-bin are required to build an archive"
        )
    helper = executable(args.code_mode_host_bin, "code-mode host")
    if args.app_server_bin is not None:
        app_server = executable(args.app_server_bin, "Codex app-server")
    else:
        target_dir = args.cargo_target_dir or default_target_dir()
        app_server = executable(
            build_app_server(args.target, target_dir, args.jobs),
            "built Codex app-server",
        )
    archive = write_archive(
        args.output_dir.resolve(), args.release_tag, args.target, app_server, helper
    )
    print(f"archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
