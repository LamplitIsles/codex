#!/usr/bin/env python3
import os
import signal
import subprocess
import tempfile
import time
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

    def test_sigterm_cleans_child_and_descendant_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "owned-process-group"
            program = (
                "import os,pathlib,subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)"
            )
            wrapper = subprocess.Popen(
                [
                    sys.executable,
                    str(GUARD),
                    "--free-disk-mib",
                    "0",
                    "--",
                    sys.executable,
                    "-c",
                    program,
                    str(marker),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            group = None
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.025)
                self.assertTrue(marker.exists(), "test-owned descendants must start")
                group = int(marker.read_text())
                wrapper.terminate()
                wrapper.wait(timeout=5)
                while time.monotonic() < deadline:
                    states = subprocess.check_output(
                        ["ps", "-axo", "pgid=,stat="], text=True
                    )
                    live = [
                        state
                        for line in states.splitlines()
                        for pgid, state in [line.split()]
                        if int(pgid) == group and not state.startswith("Z")
                    ]
                    if not live:
                        break
                    time.sleep(0.025)
                self.assertEqual(
                    live, [], "termination must stop the owned child group"
                )
                self.assertEqual(wrapper.returncode, 128 + signal.SIGTERM)
            finally:
                if group is not None:
                    try:
                        os.killpg(group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if wrapper.poll() is None:
                    wrapper.kill()
                wrapper.wait()

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
