#!/usr/bin/env python3
import argparse
import json
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live HTTP checks against navparse endpoints.")
    parser.add_argument("--startup-timeout", type=float, default=10.0, help="Seconds to wait for navparse HTTP startup.")
    parser.add_argument("--request-timeout", type=float, default=2.0, help="Per-request timeout in seconds.")
    parser.add_argument("--binary", default="navparse", help="Path to navparse binary (default: navparse in repo root).")
    parser.add_argument("--html-dir", default="html", help="HTML directory path passed to navparse --html.")
    return parser.parse_args()


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    if port <= 1024:
        raise RuntimeError(f"Reserved invalid test port {port}")
    return port


def request_json(
    base_url: str, method: str, path: str, timeout: float, extra_headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], object]:
    headers = {"Content-Type": "text/plain"}
    if extra_headers:
        headers.update(extra_headers)
    req = Request(
        f"{base_url}{path}",
        method=method,
        data=(b"" if method == "POST" else None),
        headers=headers,
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, json.loads(body)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path}: HTTP {e.code}, body={body}") from e
    except URLError as e:
        raise RuntimeError(f"{method} {path}: URL error: {e}") from e


def wait_until_ready(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, headers, payload = request_json(base_url, "GET", "/global.json", 0.5)
            if status == 200 and "application/json" in headers.get("content-type", "") and isinstance(payload, dict):
                return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("navparse did not become ready before timeout")


def assert_json_response(
    base_url: str,
    method: str,
    path: str,
    request_timeout: float,
    validator,
    extra_headers: dict[str, str] | None = None,
) -> None:
    status, headers, payload = request_json(base_url, method, path, request_timeout, extra_headers=extra_headers)
    if status != 200:
        raise RuntimeError(f"{method} {path}: expected HTTP 200, got {status}")
    if "application/json" not in headers.get("content-type", ""):
        raise RuntimeError(f"{method} {path}: expected JSON content-type, got {headers.get('content-type', '<missing>')}")
    validator(payload)


def validate_mapping_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object, got {type(payload).__name__}")


def validate_sequence_payload(payload: object) -> None:
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected JSON array, got {type(payload).__name__}")


def validate_sv_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object, got {type(payload).__name__}")
    for key in ("sv", "gnssid", "sigid"):
        if key not in payload:
            raise RuntimeError(f"/sv.json missing key '{key}' in payload")
    if payload["sv"] != 12:
        raise RuntimeError(f"/sv.json unexpected sv value: {payload['sv']}")
    if payload["gnssid"] != 2:
        raise RuntimeError(f"/sv.json unexpected gnssid value: {payload['gnssid']}")
    if payload["sigid"] != 5:
        raise RuntimeError(f"/sv.json unexpected sigid value: {payload['sigid']}")


def run_endpoint_checks(base_url: str, request_timeout: float) -> None:
    client_profiles: list[tuple[str, dict[str, str]]] = [
        ("unauthenticated", {}),
        ("basic-auth-header", {"Authorization": "Basic dGVzdDp0ZXN0"}),
        ("bearer-auth-header", {"Authorization": "Bearer test-token"}),
    ]
    checks: list[tuple[str, str, Callable[[object], None]]] = [
        ("/global.json", "mapping", validate_mapping_payload),
        ("/almanac.json", "mapping", validate_mapping_payload),
        ("/observers.json", "sequence", validate_sequence_payload),
        ("/sv.json?sv=12&gnssid=2&sigid=5", "sv", validate_sv_payload),
        ("/cov.json?gps=1&galileo=1&beidou=1&glonass=1", "sequence", validate_sequence_payload),
        ("/sbas.json", "mapping", validate_mapping_payload),
        ("/svs.json", "mapping", validate_mapping_payload),
        ("/sbstatus.json", "sequence", validate_sequence_payload),
    ]
    for path, shape, validator in checks:
        for client_label, auth_headers in client_profiles:
            for method in ("GET", "POST"):
                assert_json_response(base_url, method, path, request_timeout, validator, extra_headers=auth_headers)
                print(f"{method} {path}: OK ({shape}, {client_label})")


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    binary = (root / args.binary).resolve()
    html_dir = (root / args.html_dir).resolve()
    if not binary.exists():
        print(f"error: missing navparse binary at {binary}", file=sys.stderr)
        return 2
    if not html_dir.exists():
        print(f"error: missing HTML directory at {html_dir}", file=sys.stderr)
        return 2

    port = reserve_port()
    bind_address = f"127.0.0.1:{port}"
    base_url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [str(binary), "--bind", bind_address, "--html", str(html_dir)],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        wait_until_ready(base_url, args.startup_timeout)
        run_endpoint_checks(base_url, args.request_timeout)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3.0)


if __name__ == "__main__":
    sys.exit(main())
