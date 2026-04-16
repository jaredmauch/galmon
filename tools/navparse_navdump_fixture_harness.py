#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def normalize_version_text(text: str) -> str:
    # Normalize the git hash suffix in: "galmon tools (name) <hash>"
    text = re.sub(r"^(galmon tools \([^)]+\))\s+\S+$", r"\1 <HASH>", text, flags=re.MULTILINE)
    # Normalize compiler date line.
    text = re.sub(r"^built date .+$", "built date <BUILD_DATE>", text, flags=re.MULTILINE)
    return text.strip()


def run_and_capture(
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
    expected_path = root / "tests" / "golden" / f"{app}.version.txt"

    rc, out = run_and_capture(
        binary, ["--version"], use_valgrind=use_valgrind, valgrind_error_exitcode=valgrind_error_exitcode
    )
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


def assert_navdump_garbage_input(root: Path, use_valgrind: bool, valgrind_error_exitcode: int) -> bool:
    binary = root / "navdump"
    cmd = [str(binary)]
    if use_valgrind:
        cmd = [
            "valgrind",
            "--quiet",
            "--leak-check=full",
            "--show-leak-kinds=all",
            "--errors-for-leak-kinds=definite,possible,indirect",
            f"--error-exitcode={valgrind_error_exitcode}",
        ] + cmd
    proc = subprocess.run(
        cmd,
        input=b"\x00\x01garbage\n\xff\xfe",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.returncode < 0:
        print(f"navdump: crashed with signal {-proc.returncode} on garbage stdin")
        return False
    print(f"navdump: garbage-stdin exit={proc.returncode}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixture checks for navparse/navdump.")
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
    failed = False

    for app in ("navparse", "navdump"):
        if not assert_version_golden(root, app, args.valgrind, args.valgrind_error_exitcode):
            failed = True

    if not assert_navdump_garbage_input(root, args.valgrind, args.valgrind_error_exitcode):
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
