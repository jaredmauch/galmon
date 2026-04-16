#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


def normalize_version_text(text: str) -> str:
    # Normalize the git hash suffix in: "galmon tools (name) <hash>"
    text = re.sub(r"^(galmon tools \([^)]+\))\s+\S+$", r"\1 <HASH>", text, flags=re.MULTILINE)
    # Normalize compiler date line.
    text = re.sub(r"^built date .+$", "built date <BUILD_DATE>", text, flags=re.MULTILINE)
    return text.strip()


def run_and_capture(binary: Path, args: list[str]) -> tuple[int, str]:
    proc = subprocess.run([str(binary)] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout.strip()


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


def assert_navdump_garbage_input(root: Path) -> bool:
    binary = root / "navdump"
    proc = subprocess.run(
        [str(binary)],
        input=b"\x00\x01garbage\n\xff\xfe",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode < 0:
        print(f"navdump: crashed with signal {-proc.returncode} on garbage stdin")
        return False
    print(f"navdump: garbage-stdin exit={proc.returncode}")
    return True


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    failed = False

    for app in ("navparse", "navdump"):
        if not assert_version_golden(root, app):
            failed = True

    if not assert_navdump_garbage_input(root):
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
