#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PROGRAMS = [
    "navparse",
    "ubxtool",
    "navnexus",
    "navcat",
    "navrecv",
    "navdump",
    "testrunner",
    "navdisplay",
    "tlecatch",
    "reporter",
    "sp3feed",
    "galmonmon",
    "rinreport",
    "rinjoin",
    "rtcmtool",
    "gndate",
    "septool",
    "navmerge",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a quick crash-safety smoke check over all compiled applications.")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="Per-app timeout in seconds (default: 5).")
    parser.add_argument("--version-flag", default="--version", help="Flag passed to each binary (default: --version).")
    parser.add_argument("--valgrind", action="store_true", help="Run each app invocation under valgrind memcheck.")
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
    for program in PROGRAMS:
        binary = root / program
        if not binary.exists():
            print(f"{program}: missing binary (build first)")
            failed = True
            continue

        try:
            cmd = [str(binary), args.version_flag]
            if args.valgrind:
                cmd = [
                    "valgrind",
                    "--quiet",
                    "--leak-check=full",
                    "--show-leak-kinds=all",
                    "--errors-for-leak-kinds=definite,possible,indirect",
                    f"--error-exitcode={args.valgrind_error_exitcode}",
                ] + cmd
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=args.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            print(f"{program}: timeout (> {args.timeout_seconds}s)")
            failed = True
            continue

        if proc.returncode < 0:
            print(f"{program}: crashed with signal {-proc.returncode}")
            failed = True
        elif args.valgrind and proc.returncode == args.valgrind_error_exitcode:
            print(f"{program}: valgrind reported memory errors (exit={proc.returncode})")
            failed = True
        else:
            print(f"{program}: exit={proc.returncode}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
