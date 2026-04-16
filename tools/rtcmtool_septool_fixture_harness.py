#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


def normalize_version_text(text: str) -> str:
    text = re.sub(r"^(galmon tools \([^)]+\))\s+\S+$", r"\1 <HASH>", text, flags=re.MULTILINE)
    text = re.sub(r"^built date .+$", "built date <BUILD_DATE>", text, flags=re.MULTILINE)
    return text.strip()


def run_and_capture(binary: Path, args: list[str], data: bytes | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        [str(binary)] + args,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace").strip()


def assert_version_golden(root: Path, app: str) -> bool:
    binary = root / app
    expected_path = root / "tests" / "golden" / f"{app}.version.txt"

    rc, out = run_and_capture(binary, ["--version"])
    norm = normalize_version_text(out)
    expected = expected_path.read_text().strip()

    if rc != 0:
        print(f"{app}: expected exit=0 for --version, got {rc}")
        return False
    if norm != expected:
        print(f"{app}: version output mismatch")
        print("---- expected ----")
        print(expected)
        print("---- actual ----")
        print(norm)
        return False
    print(f"{app}: version golden match")
    return True


def assert_garbage_stdin_no_crash(root: Path, app: str, args: list[str]) -> bool:
    binary = root / app
    rc, _out = run_and_capture(binary, args, data=b"\x00\x01garbage\n\xff\xfe")
    if rc < 0:
        print(f"{app}: crashed with signal {-rc} on garbage stdin")
        return False
    print(f"{app}: garbage-stdin exit={rc}")
    return True


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    failed = False

    for app in ("rtcmtool", "septool"):
        if not assert_version_golden(root, app):
            failed = True

    # Required options for parser loops; verify malformed streams don't crash.
    if not assert_garbage_stdin_no_crash(root, "rtcmtool", ["--station", "1"]):
        failed = True
    if not assert_garbage_stdin_no_crash(root, "septool", ["--station", "1"]):
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
