#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def normalize_version_text(text: str) -> str:
    text = re.sub(r"^(galmon tools \([^)]+\))\s+\S+$", r"\1 <HASH>", text, flags=re.MULTILINE)
    text = re.sub(r"^built date .+$", "built date <BUILD_DATE>", text, flags=re.MULTILINE)
    return text.strip()


def run_and_capture(
    binary: Path,
    args: list[str],
    data: bytes | None = None,
    use_valgrind: bool = False,
    valgrind_error_exitcode: int = 99,
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
    proc = subprocess.run(
        cmd,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace").strip()


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


def assert_garbage_stdin_no_crash(
    root: Path, app: str, args: list[str], use_valgrind: bool, valgrind_error_exitcode: int
) -> bool:
    binary = root / app
    rc, _out = run_and_capture(
        binary,
        args,
        data=b"\x00\x01garbage\n\xff\xfe",
        use_valgrind=use_valgrind,
        valgrind_error_exitcode=valgrind_error_exitcode,
    )
    if rc < 0:
        print(f"{app}: crashed with signal {-rc} on garbage stdin")
        return False
    print(f"{app}: garbage-stdin exit={rc}")
    return True


def build_septentrio_frame(message_id: int, payload: bytes) -> bytes:
    # Layout expected by getSEPMessage():
    # '$@' + 2 CRC bytes + 2 block-id bytes + 2 length bytes + payload
    total_len = 8 + len(payload)
    if total_len > 0xFFFF:
        raise ValueError("payload too large for synthetic Septentrio frame")
    return b"$@" + b"\x00\x00" + message_id.to_bytes(2, "little") + total_len.to_bytes(2, "little") + payload


def assert_septool_short_inav_payload(root: Path, use_valgrind: bool, valgrind_error_exitcode: int) -> bool:
    binary = root / "septool"
    # 4023 is the I/NAV block handled early in septool; a short payload should be skipped cleanly.
    frame = build_septentrio_frame(4023, b"\x00" * 8)
    rc, out = run_and_capture(
        binary,
        ["--station", "1"],
        data=frame,
        use_valgrind=use_valgrind,
        valgrind_error_exitcode=valgrind_error_exitcode,
    )
    if rc != 0:
        print(f"septool: short-inav expected exit=0, got {rc}")
        print(out)
        return False
    if "Short SEPInav payload, skipping" not in out:
        print("septool: short-inav did not report defensive short-payload handling")
        print(out)
        return False
    print("septool: short-inav payload handled safely")
    return True


def assert_septool_unknown_message_logging(
    root: Path, quiet: bool, use_valgrind: bool, valgrind_error_exitcode: int
) -> bool:
    binary = root / "septool"
    frame = build_septentrio_frame(999, b"\x00" * 4)
    args = ["--station", "1"]
    label = "unknown-message"
    if quiet:
        args.extend(["--quiet", "true"])
        label += "-quiet"
    rc, out = run_and_capture(
        binary,
        args,
        data=frame,
        use_valgrind=use_valgrind,
        valgrind_error_exitcode=valgrind_error_exitcode,
    )
    if rc != 0:
        print(f"septool: {label} expected exit=0, got {rc}")
        print(out)
        return False
    has_unknown = "Unknown message 999 / 999" in out
    if quiet and has_unknown:
        print("septool: --quiet should suppress unknown-message log output")
        print(out)
        return False
    if not quiet and not has_unknown:
        print("septool: unknown-message path did not emit expected diagnostic")
        print(out)
        return False
    print(f"septool: {label} branch behaved as expected")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixture checks for rtcmtool/septool.")
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

    for app in ("rtcmtool", "septool"):
        if not assert_version_golden(root, app, args.valgrind, args.valgrind_error_exitcode):
            failed = True

    # Required options for parser loops; verify malformed streams don't crash.
    if not assert_garbage_stdin_no_crash(
        root, "rtcmtool", ["--station", "1"], args.valgrind, args.valgrind_error_exitcode
    ):
        failed = True
    if not assert_garbage_stdin_no_crash(
        root, "septool", ["--station", "1"], args.valgrind, args.valgrind_error_exitcode
    ):
        failed = True
    if not assert_septool_short_inav_payload(root, args.valgrind, args.valgrind_error_exitcode):
        failed = True
    if not assert_septool_unknown_message_logging(root, False, args.valgrind, args.valgrind_error_exitcode):
        failed = True
    if not assert_septool_unknown_message_logging(root, True, args.valgrind, args.valgrind_error_exitcode):
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
