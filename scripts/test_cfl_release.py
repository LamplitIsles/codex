#!/usr/bin/env python3
import json
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("cfl_release.py")


def fake_executable(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class CflReleaseTest(unittest.TestCase):
    def test_archives_are_self_describing_and_manifest_covers_both_targets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_server = root / "codex-app-server"
            helper = root / "codex-code-mode-host"
            fake_executable(app_server, b"app-server fixture")
            fake_executable(helper, b"helper fixture")
            output = root / "output"
            for target in ("x86_64-unknown-linux-musl",):
                subprocess.check_call(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--target",
                        target,
                        "--release-tag",
                        "cfl/v0.154.0-rc.1",
                        "--output-dir",
                        str(output),
                        "--app-server-bin",
                        str(app_server),
                        "--code-mode-host-bin",
                        str(helper),
                    ]
                )
            archives = sorted(output.glob("*.tar.gz"))
            self.assertEqual(len(archives), 1)
            subprocess.check_call(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--output-dir",
                    str(output),
                    "--finalize-checksums",
                ]
            )
            manifest = (output / "SHA256SUMS").read_text()
            self.assertTrue(all(archive.name in manifest for archive in archives))
            with tarfile.open(archives[0]) as archive:
                names = archive.getnames()
                self.assertTrue(
                    any(name.endswith("/bin/codex-app-server") for name in names)
                )
                self.assertTrue(
                    any(name.endswith("/bin/codex-code-mode-host") for name in names)
                )
                provenance_name = next(
                    name for name in names if name.endswith("/provenance.json")
                )
                provenance = json.load(archive.extractfile(provenance_name))
            self.assertEqual(provenance["target"], "x86_64-unknown-linux-musl")
            self.assertFalse(str(root) in json.dumps(provenance))

    def test_checksum_finalization_rejects_stale_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "cfl-codex-app-server-stale-aarch64-apple-darwin.tar.gz").touch()
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--output-dir",
                    str(output),
                    "--finalize-checksums",
                ],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one archive", result.stderr)

    def test_rejects_unsupported_target(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--target", "x86_64-pc-windows-msvc"],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)

    def test_rejects_non_positive_job_override(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--target",
                "x86_64-unknown-linux-musl",
                "--jobs",
                "0",
            ],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integer", result.stderr)

    def test_rejects_unsupported_source_build_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            helper = Path(temporary) / "codex-code-mode-host"
            fake_executable(helper, b"helper fixture")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--target",
                    "aarch64-apple-darwin",
                    "--release-tag",
                    "cfl/v0.154.0-rc.1",
                    "--output-dir",
                    temporary,
                    "--code-mode-host-bin",
                    str(helper),
                ],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
