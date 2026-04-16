#!/usr/bin/env python3
import argparse
import random
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


def get_valgrind_prefix(error_exitcode: int) -> list[str]:
    return [
        "valgrind",
        "--quiet",
        "--leak-check=full",
        "--show-leak-kinds=all",
        "--errors-for-leak-kinds=definite,possible,indirect",
        f"--error-exitcode={error_exitcode}",
    ]


def build_random_blob(seed: int, size: int) -> bytes:
    rng = random.Random(seed)
    return bytes(rng.getrandbits(8) for _ in range(size))


def build_malformed_blob() -> bytes:
    # Mixed binary garbage with truncated framing-like markers.
    return b"\xb5\x62\x01\x07\xff\xff\x00\x00garbage\xff\xfe\n\x80\x81"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run crash-safety checks over all compiled applications.")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="Per-app timeout in seconds (default: 5).")
    parser.add_argument("--version-flag", default="--version", help="Flag passed to each binary (default: --version).")
    parser.add_argument("--random-bytes", type=int, default=512, help="Random-input payload size (default: 512).")
    parser.add_argument("--seed", type=int, default=20260416, help="Seed for deterministic random input (default: 20260416).")
    parser.add_argument("--valgrind", action="store_true", help="Run each app invocation under valgrind memcheck.")
    parser.add_argument(
        "--valgrind-error-exitcode",
        type=int,
        default=99,
        help="Exit code valgrind uses when memory errors are detected (default: 99).",
    )
    return parser.parse_args()


def run_case(
    program: str,
    binary: Path,
    case_name: str,
    app_args: list[str],
    stdin_data: bytes | None,
    timeout_seconds: float,
    use_valgrind: bool,
    valgrind_error_exitcode: int,
) -> tuple[bool, str]:
    cmd = [str(binary)] + app_args
    if use_valgrind:
        cmd = get_valgrind_prefix(valgrind_error_exitcode) + cmd
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return False, f"{program}:{case_name}: timeout (> {timeout_seconds}s)"

    if proc.returncode < 0:
        return False, f"{program}:{case_name}: crashed with signal {-proc.returncode}"
    if use_valgrind and proc.returncode == valgrind_error_exitcode:
        return False, f"{program}:{case_name}: valgrind reported memory errors (exit={proc.returncode})"
    return True, f"{program}:{case_name}: exit={proc.returncode}"


def main() -> int:
    args = parse_args()
    if args.random_bytes < 1:
        print("error: --random-bytes must be >= 1", file=sys.stderr)
        return 2
    if args.valgrind and not shutil.which("valgrind"):
        print("error: --valgrind requested, but valgrind is not installed", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent
    malformed_blob = build_malformed_blob()

    failed = False
    for program in PROGRAMS:
        binary = root / program
        if not binary.exists():
            print(f"{program}: missing binary (build first)")
            failed = True
            continue

        random_blob = build_random_blob(args.seed + len(program), args.random_bytes)
        cases = [
            ("valid", [args.version_flag], None),
            ("random", [], random_blob),
            ("malformed", [], malformed_blob),
        ]
        for case_name, app_args, stdin_data in cases:
            ok, message = run_case(
                program,
                binary,
                case_name,
                app_args,
                stdin_data,
                args.timeout_seconds,
                args.valgrind,
                args.valgrind_error_exitcode,
            )
            print(message)
            if not ok:
                failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
