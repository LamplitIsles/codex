#!/usr/bin/env python3
import subprocess
import sys
import unittest
from pathlib import Path


GUARD = Path(__file__).with_name("cfl_build_guard.py")


class BuildGuardTest(unittest.TestCase):
    def run_guard(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(GUARD), "--free-disk-mib", "0", *args],
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_preserves_command_exit_status(self) -> None:
        result = self.run_guard("--", sys.executable, "-c", "raise SystemExit(7)")
        self.assertEqual(result.returncode, 7)

    def test_enforces_aggregate_descendant_memory(self) -> None:
        # Each child fits below the cap; the process group exceeds it together.
        program = (
            "import subprocess,sys,time; "
            "[subprocess.Popen([sys.executable, '-c', "
            "'import time; a=bytearray(48*1024*1024); time.sleep(30)']) "
            "for _ in range(2)]; time.sleep(30)"
        )
        result = self.run_guard(
            "--memory-mib", "80", "--", sys.executable, "-c", program
        )
        self.assertEqual(result.returncode, 75)
        self.assertIn("aggregate RSS", result.stdout)

    def test_enforces_runtime(self) -> None:
        result = self.run_guard(
            "--seconds",
            "0.1",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        )
        self.assertEqual(result.returncode, 75)
        self.assertIn("runtime", result.stdout)


if __name__ == "__main__":
    unittest.main()
