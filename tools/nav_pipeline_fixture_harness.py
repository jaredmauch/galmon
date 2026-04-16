#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


def normalize_version_text(text: str) -> str:
    text = re.sub(r"^(galmon tools \([^)]+\))\s+\S+$", r"\1 <HASH>", text, flags=re.MULTILINE)
    text = re.sub(r"^built date .+$", "built date <BUILD_DATE>", text, flags=re.MULTILINE)
    return text.strip()


def run(binary: Path, args: list[str], timeout: float = 5.0) -> tuple[int, str]:
    proc = subprocess.run(
        [str(binary)] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip()


def assert_version_golden(root: Path, app: str) -> bool:
    binary = root / app
    expected = (root / "tests" / "golden" / f"{app}.version.txt").read_text().strip()
    rc, out = run(binary, ["--version"])
    norm = normalize_version_text(out)
    if rc != 0 or norm != expected:
        print(f"{app}: version check failed")
        return False
    print(f"{app}: version golden match")
    return True


def assert_help_exits(root: Path, app: str) -> bool:
    rc, _out = run(root / app, ["--help"])
    if rc != 0:
        print(f"{app}: --help returned {rc}, expected 0")
        return False
    print(f"{app}: --help check ok")
    return True


def assert_expected_error(root: Path, app: str, args: list[str], expected_rc: int, expected_substr: str) -> bool:
    rc, out = run(root / app, args)
    if rc != expected_rc or expected_substr not in out:
        print(f"{app}: expected rc={expected_rc} and message '{expected_substr}'")
        return False
    print(f"{app}: edge-case check ok")
    return True


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    checks = [
        assert_version_golden(root, "navrecv"),
        assert_version_golden(root, "navmerge"),
        assert_version_golden(root, "navcat"),
        assert_version_golden(root, "navnexus"),
        assert_help_exits(root, "navrecv"),
        assert_help_exits(root, "navnexus"),
        assert_expected_error(root, "navmerge", [], 0, "No sources defined. Exiting."),
        assert_expected_error(root, "navcat", [], 1, "No time range specified"),
    ]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
