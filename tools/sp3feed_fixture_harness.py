#!/usr/bin/env python3
import argparse
import http.server
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class _CaptureHandler(http.server.BaseHTTPRequestHandler):
    requests = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        self.__class__.requests.append((self.path, body))
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an integration fixture against sp3feed.")
    parser.add_argument("--binary", default="sp3feed", help="Path to sp3feed binary (default: repo-root ./sp3feed).")
    return parser.parse_args()


def make_synthetic_sp3() -> str:
    return (
        "*  2026  4 16 12 34 56.00000000\n"
        "PG12  12345.678901  -23456.789012   34567.890123    123.456789\n"
        "PE11  -1000.000000   2000.500000   -3000.250000    -10.000000\n"
    )


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    binary = (root / args.binary).resolve()
    if not binary.exists():
      print(f"error: missing sp3feed binary at {binary}", file=sys.stderr)
      return 2

    _CaptureHandler.requests.clear()
    server = _ThreadingTCPServer(("127.0.0.1", 8086), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    with tempfile.NamedTemporaryFile("w", suffix=".sp3", delete=False) as fp:
        fp.write(make_synthetic_sp3())
        sp3_path = Path(fp.name)

    try:
        proc = subprocess.run(
            [str(binary), "--influxdb", "testdb", "--sp3src", "fixture", str(sp3_path)],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)
        sp3_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        print(proc.stdout, end="", file=sys.stdout)
        print(proc.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"sp3feed exited with {proc.returncode}")

    if str(sp3_path) not in proc.stdout:
        raise RuntimeError("sp3feed stdout did not mention the input SP3 file")

    if not _CaptureHandler.requests:
        raise RuntimeError("expected at least one POST to Influx, got none")

    expected_lines = [
        'sp3,gnssid=0,sv=12,sp3src=fixture x=12345678.901000,y=-23456789.012000,z=34567890.123000,clock-bias=123456.789000 1776342896000000000',
        'sp3,gnssid=2,sv=11,sp3src=fixture x=-1000000.000000,y=2000500.000000,z=-3000250.000000,clock-bias=-10000.000000 1776342896000000000',
    ]
    got_lines: list[str] = []
    for path, body in _CaptureHandler.requests:
        if path != "/write?db=testdb":
            raise RuntimeError(f"unexpected Influx write path: {path}")
        got_lines.extend(line for line in body.splitlines() if line)
    if sorted(got_lines) != sorted(expected_lines):
        raise RuntimeError(f"unexpected Influx line protocol:\nexpected={expected_lines}\ngot={got_lines}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
