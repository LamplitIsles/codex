#!/usr/bin/env python3
"""Bound a native Mac build's process group when taskpolicy limits are advisory."""

import argparse
import os
import shutil
import signal
import subprocess
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-mib", type=int, default=6144)
    parser.add_argument("--tasks", type=int, default=256)
    parser.add_argument("--seconds", type=float, default=3600)
    parser.add_argument("--free-disk-mib", type=int, default=2048)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command or min(args.memory_mib, args.tasks, args.seconds) <= 0:
        parser.error("a command and positive resource limits are required")
    if args.free_disk_mib < 0:
        parser.error("free disk limit must be nonnegative")

    deadline = time.monotonic() + args.seconds
    child = subprocess.Popen(command, start_new_session=True)
    try:
        while child.poll() is None:
            output = subprocess.check_output(["ps", "-axo", "pgid=,rss="], text=True)
            usage = [
                int(rss)
                for line in output.splitlines()
                for group, rss in [line.split()]
                if int(group) == child.pid
            ]
            reason = None
            if sum(usage) > args.memory_mib * 1024:
                reason = "aggregate RSS"
            elif len(usage) > args.tasks:
                reason = "process count"
            elif time.monotonic() >= deadline:
                reason = "runtime"
            elif shutil.disk_usage(".").free < args.free_disk_mib * 1024 * 1024:
                reason = "free disk"
            if reason:
                print(f"build guard: {reason} limit exceeded", flush=True)
                return 75
            time.sleep(0.25)
        return child.returncode
    finally:
        # This group belongs exclusively to the command launched above. Kill any
        # surviving descendants on failure, interruption or parent completion.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
