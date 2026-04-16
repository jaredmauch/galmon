#!/usr/bin/env python3
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def normalize_version_text(text: str) -> str:
    text = re.sub(r"^(galmon tools \([^)]+\))\s+\S+$", r"\1 <HASH>", text, flags=re.MULTILINE)
    text = re.sub(r"^built date .+$", "built date <BUILD_DATE>", text, flags=re.MULTILINE)
    return text.strip()


def run(binary: Path, args: list[str]) -> tuple[int, str]:
    proc = subprocess.run([str(binary)] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout.strip()


def assert_version_golden(root: Path, app: str) -> bool:
    binary = root / app
    expected = (root / "tests" / "golden" / f"{app}.version.txt").read_text().strip()

    rc, out = run(binary, ["--version"])
    norm = normalize_version_text(out)
    if rc != 0:
        print(f"{app}: expected exit=0 for --version, got {rc}")
        return False
    if norm != expected:
        print(f"{app}: version output mismatch")
        return False
    print(f"{app}: version golden match")
    return True


def assert_missing_args(root: Path) -> bool:
    ok = True
    rc, out = run(root / "rinreport", [])
    if rc != 1 or "Need an input file containing RINEX paths" not in out:
        print("rinreport: missing-arg behavior mismatch")
        ok = False
    else:
        print("rinreport: missing-arg check ok")

    rc, out = run(root / "rinjoin", [])
    if rc != 1 or "Need at least one input RINEX file" not in out:
        print("rinjoin: missing-arg behavior mismatch")
        ok = False
    else:
        print("rinjoin: missing-arg check ok")
    return ok


def assert_rinreport_bad_input_list(root: Path) -> bool:
    bogus_path = "/definitely/not/here/list.txt"
    rc, out = run(root / "rinreport", [bogus_path])
    if rc != 1 or "Unable to open input file list" not in out:
        print("rinreport: bad input-list path behavior mismatch")
        return False
    print("rinreport: bad input-list path check ok")
    return True


def assert_rinjoin_nonexistent_file(root: Path) -> bool:
    rc, out = run(root / "rinjoin", ["/definitely/not/here/file.rnx"])
    if rc != 0 or "Error processing file" not in out:
        print("rinjoin: nonexistent-input behavior mismatch")
        return False
    print("rinjoin: nonexistent-input check ok")
    return True


def assert_rinreport_empty_list(root: Path) -> bool:
    with tempfile.NamedTemporaryFile(prefix="rinreport-empty-", suffix=".txt", mode="w", delete=True) as fp:
        rc, out = run(root / "rinreport", [fp.name])
    if rc != 0 or "All slots:" not in out:
        print("rinreport: empty list behavior mismatch")
        return False
    print("rinreport: empty list check ok")
    return True


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    checks = [
        assert_version_golden(root, "rinreport"),
        assert_version_golden(root, "rinjoin"),
        assert_missing_args(root),
        assert_rinreport_bad_input_list(root),
        assert_rinjoin_nonexistent_file(root),
        assert_rinreport_empty_list(root),
    ]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
