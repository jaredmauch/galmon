#!/usr/bin/env python3
import os
import argparse
import random
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def ubx_checksum(ubx_class: int, ubx_type: int, payload: bytes) -> bytes:
    ck_a = 0
    ck_b = 0
    for b in bytes([ubx_class, ubx_type]) + struct.pack("<H", len(payload)) + payload:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return bytes([ck_a, ck_b])


def build_ubx(ubx_class: int, ubx_type: int, payload: bytes) -> bytes:
    return b"\xb5\x62" + bytes([ubx_class, ubx_type]) + struct.pack("<H", len(payload)) + payload + ubx_checksum(ubx_class, ubx_type, payload)


def nav_pvt_payload() -> bytes:
    # 92-byte UBX-NAV-PVT payload with a valid UTC date/time and fix type.
    payload = bytearray(92)
    struct.pack_into("<I", payload, 0, 123000)  # iTOW
    struct.pack_into("<H", payload, 4, 2026)  # year
    payload[6] = 4  # month
    payload[7] = 16  # day
    payload[8] = 12  # hour
    payload[9] = 34  # minute
    payload[10] = 56  # second
    payload[11] = 0x07  # valid date+time flags
    struct.pack_into("<i", payload, 16, 250000000)  # nano
    payload[20] = 3  # fix type
    struct.pack_into("<i", payload, 60, 1500)  # gSpeed mm/s
    return bytes(payload)


def run_case(
    ubxtool_bin: Path,
    name: str,
    data: bytes,
    extra_args: list[str] | None = None,
    use_valgrind: bool = False,
    valgrind_error_exitcode: int = 99,
) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(prefix=f"ubxtool-{name}-", suffix=".ubx", delete=False) as fp:
        fp.write(data)
        testfile = fp.name

    cmd = [str(ubxtool_bin), "--port", testfile, "--station", "1", "--stdout"]
    if extra_args:
        cmd.extend(extra_args)
    if use_valgrind:
        cmd = [
            "valgrind",
            "--quiet",
            "--leak-check=full",
            "--show-leak-kinds=all",
            "--errors-for-leak-kinds=definite,possible,indirect",
            f"--error-exitcode={valgrind_error_exitcode}",
        ] + cmd
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.unlink(testfile)

    stderr_text = proc.stderr.decode("utf-8", errors="replace")
    stderr_tail = "\n".join(stderr_text.strip().splitlines()[-10:])
    if proc.returncode == valgrind_error_exitcode:
        return False, f"{name}: valgrind reported memory errors (exit {proc.returncode})\n{stderr_tail}"
    if proc.returncode < 0:
        sig = -proc.returncode
        return False, f"{name}: crashed with signal {sig}\n{stderr_tail}"
    if use_valgrind:
        return True, f"{name}: exit={proc.returncode}"
    return True, f"{name}: exit={proc.returncode}\n{stderr_tail}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run crash-safety checks against ubxtool.")
    parser.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="Number of deterministic randomized mixed-input cases to run (default: 50).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260416,
        help="Random seed for deterministic randomized cases (default: 20260416).",
    )
    parser.add_argument(
        "--valgrind",
        action="store_true",
        help="Run each ubxtool invocation under valgrind memcheck.",
    )
    parser.add_argument(
        "--valgrind-error-exitcode",
        type=int,
        default=99,
        help="Exit code valgrind uses when memory errors are detected (default: 99).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iterations < 0:
        print("error: --iterations must be >= 0", file=sys.stderr)
        return 2
    if args.valgrind and not shutil.which("valgrind"):
        print("error: --valgrind requested, but valgrind is not installed", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    ubxtool_bin = repo_root / "ubxtool"
    if not ubxtool_bin.exists():
        print("error: ubxtool binary not found. Build it first with `make ubxtool`.", file=sys.stderr)
        return 2

    cases: list[tuple[str, bytes, list[str]]] = []

    # Baseline sane stream: valid timestamp message then EOF.
    cases.append(("file-input-no-baud", build_ubx(0x01, 0x07, nav_pvt_payload()), []))
    cases.append(("baseline-nav-pvt", build_ubx(0x01, 0x07, nav_pvt_payload()), ["--baud", "9600"]))

    # Truncated marker/header stream.
    cases.append(("truncated-header", b"\xb5\x62\x01", ["--baud", "9600"]))

    # Valid timestamp, then NAV-SIG payload that claims many entries with too-short body.
    sig_short = bytearray(8)
    sig_short[5] = 200
    cases.append(
        (
            "nav-sig-short",
            build_ubx(0x01, 0x07, nav_pvt_payload()) + build_ubx(0x01, 0x43, bytes(sig_short)),
            ["--baud", "9600"],
        )
    )

    # Valid timestamp, then NAV-SAT payload that claims many entries with too-short body.
    sat_short = bytearray(8)
    sat_short[5] = 200
    cases.append(
        (
            "nav-sat-short",
            build_ubx(0x01, 0x07, nav_pvt_payload()) + build_ubx(0x01, 0x35, bytes(sat_short)),
            ["--baud", "9600"],
        )
    )

    # Header and checksum corruption cases.
    pvt = build_ubx(0x01, 0x07, nav_pvt_payload())
    cases.append(("single-byte-input", b"\x00", ["--baud", "9600"]))
    cases.append(("marker-only", b"\xb5\x62", ["--baud", "9600"]))
    cases.append(("truncated-after-length", pvt[:6], ["--baud", "9600"]))
    cases.append(("truncated-before-checksum", pvt[:-1], ["--baud", "9600"]))
    bad_ck = bytearray(pvt)
    bad_ck[-1] ^= 0xFF
    cases.append(("bad-checksum", bytes(bad_ck), ["--baud", "9600"]))

    # A fake "very large payload length" with no payload/checksum bytes following.
    cases.append(("oversized-length-header", b"\xb5\x62\x01\x07\xff\xff", ["--baud", "9600"]))

    # Deterministic pseudo-fuzz streams: mix random bytes and occasionally valid frames.
    rng = random.Random(args.seed)
    for idx in range(args.iterations):
        blob = bytearray(rng.randbytes(1200))
        # Inject a few valid frames at random offsets so parser sees mixed input.
        for _ in range(3):
            frame = build_ubx(0x01, 0x07, nav_pvt_payload())
            off = rng.randrange(0, max(1, len(blob) - len(frame)))
            blob[off : off + len(frame)] = frame
        cases.append((f"randmix-{idx:02d}", bytes(blob), ["--baud", "9600"]))

    failed = False
    for name, data, extra_args in cases:
        ok, msg = run_case(
            ubxtool_bin,
            name,
            data,
            extra_args,
            use_valgrind=args.valgrind,
            valgrind_error_exitcode=args.valgrind_error_exitcode,
        )
        print(msg)
        if not ok:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
