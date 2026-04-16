#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def normalize_version_text(text: str) -> str:
    text = re.sub(r"^(galmon tools \([^)]+\))\s+\S+$", r"\1 <HASH>", text, flags=re.MULTILINE)
    text = re.sub(r"^built date .+$", "built date <BUILD_DATE>", text, flags=re.MULTILINE)
    return text.strip()


def run(
    binary: Path, args: list[str], use_valgrind: bool = False, valgrind_error_exitcode: int = 99
) -> tuple[int, str]:
    cmd = [str(binary)] + args
    if use_valgrind:
        cmd = [
            "valgrind",
            "--quiet",
            "--leak-check=full",
            "--show-leak-kinds=all",
            "--errors-for-leak-kinds=definite,possible,indirect",
            f"--error-exitcode={valgrind_error_exitcode}",
        ] + cmd
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout.strip()


def assert_version_golden(root: Path, app: str, use_valgrind: bool, valgrind_error_exitcode: int) -> bool:
    binary = root / app
    expected = (root / "tests" / "golden" / f"{app}.version.txt").read_text().strip()

    rc, out = run(binary, ["--version"], use_valgrind=use_valgrind, valgrind_error_exitcode=valgrind_error_exitcode)
    norm = normalize_version_text(out)
    if rc != 0:
        print(f"{app}: expected exit=0 for --version, got {rc}")
        return False
    if norm != expected:
        print(f"{app}: version output mismatch")
        return False
    print(f"{app}: version golden match")
    return True


def assert_missing_args(root: Path, use_valgrind: bool, valgrind_error_exitcode: int) -> bool:
    ok = True
    rc, out = run(
        root / "rinreport", [], use_valgrind=use_valgrind, valgrind_error_exitcode=valgrind_error_exitcode
    )
    if rc != 1 or "Need an input file containing RINEX paths" not in out:
        print("rinreport: missing-arg behavior mismatch")
        ok = False
    else:
        print("rinreport: missing-arg check ok")

    rc, out = run(root / "rinjoin", [], use_valgrind=use_valgrind, valgrind_error_exitcode=valgrind_error_exitcode)
    if rc != 1 or "Need at least one input RINEX file" not in out:
        print("rinjoin: missing-arg behavior mismatch")
        ok = False
    else:
        print("rinjoin: missing-arg check ok")
    return ok


def assert_rinreport_bad_input_list(root: Path, use_valgrind: bool, valgrind_error_exitcode: int) -> bool:
    bogus_path = "/definitely/not/here/list.txt"
    rc, out = run(
        root / "rinreport",
        [bogus_path],
        use_valgrind=use_valgrind,
        valgrind_error_exitcode=valgrind_error_exitcode,
    )
    if rc != 1 or "Unable to open input file list" not in out:
        print("rinreport: bad input-list path behavior mismatch")
        return False
    print("rinreport: bad input-list path check ok")
    return True


def assert_rinjoin_nonexistent_file(root: Path, use_valgrind: bool, valgrind_error_exitcode: int) -> bool:
    rc, out = run(
        root / "rinjoin",
        ["/definitely/not/here/file.rnx"],
        use_valgrind=use_valgrind,
        valgrind_error_exitcode=valgrind_error_exitcode,
    )
    if rc != 0 or "Error processing file" not in out:
        print("rinjoin: nonexistent-input behavior mismatch")
        return False
    print("rinjoin: nonexistent-input check ok")
    return True


def assert_rinreport_empty_list(root: Path, use_valgrind: bool, valgrind_error_exitcode: int) -> bool:
    with tempfile.NamedTemporaryFile(prefix="rinreport-empty-", suffix=".txt", mode="w", delete=True) as fp:
        rc, out = run(
            root / "rinreport",
            [fp.name],
            use_valgrind=use_valgrind,
            valgrind_error_exitcode=valgrind_error_exitcode,
        )
    if rc != 0 or "All slots:" not in out:
        print("rinreport: empty list behavior mismatch")
        return False
    print("rinreport: empty list check ok")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixture checks for rinreport/rinjoin.")
    parser.add_argument("--valgrind", action="store_true", help="Run app invocations under valgrind memcheck.")
    parser.add_argument(
        "--valgrind-error-exitcode",
        type=int,
        default=99,
        help="Exit code valgrind uses when memory errors are detected (default: 99).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.valgrind and not shutil.which("valgrind"):
        print("error: --valgrind requested, but valgrind is not installed", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent
    checks = [
        assert_version_golden(root, "rinreport", args.valgrind, args.valgrind_error_exitcode),
        assert_version_golden(root, "rinjoin", args.valgrind, args.valgrind_error_exitcode),
        assert_missing_args(root, args.valgrind, args.valgrind_error_exitcode),
        assert_rinreport_bad_input_list(root, args.valgrind, args.valgrind_error_exitcode),
        assert_rinjoin_nonexistent_file(root, args.valgrind, args.valgrind_error_exitcode),
        assert_rinreport_empty_list(root, args.valgrind, args.valgrind_error_exitcode),
    ]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
