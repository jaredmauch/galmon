#!/usr/bin/env python3
import os
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


def run_case(ubxtool_bin: Path, name: str, data: bytes, extra_args: list[str] | None = None) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(prefix=f"ubxtool-{name}-", suffix=".ubx", delete=False) as fp:
        fp.write(data)
        testfile = fp.name

    cmd = [str(ubxtool_bin), "--port", testfile, "--station", "1", "--stdout"]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.unlink(testfile)

    stderr_text = proc.stderr.decode("utf-8", errors="replace")
    stderr_tail = "\n".join(stderr_text.strip().splitlines()[-3:])
    if proc.returncode < 0:
        sig = -proc.returncode
        return False, f"{name}: crashed with signal {sig}\n{stderr_tail}"
    return True, f"{name}: exit={proc.returncode}\n{stderr_tail}"


def main() -> int:
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

    failed = False
    for name, data, extra_args in cases:
        ok, msg = run_case(ubxtool_bin, name, data, extra_args)
        print(msg)
        if not ok:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
