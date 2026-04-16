#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


def run_gcov(root: Path) -> None:
    for gcov_file in root.glob("*.gcov"):
        gcov_file.unlink()

    cc_files = sorted(
        f
        for f in root.glob("*.cc")
        if f.name not in {"navmon.pb.cc"}
    )
    if not cc_files:
        print("No .cc files found for gcov analysis.", file=sys.stderr)
        return

    cmd = ["gcov", "-p", "-o", str(root)] + [str(f) for f in cc_files]
    subprocess.run(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def parse_gcov(root: Path) -> tuple[int, int]:
    total_lines = 0
    covered_lines = 0
    line_re = re.compile(r"^\s*([^:]+):\s*\d+:")

    for gcov_file in root.glob("*.gcov"):
        text = gcov_file.read_text(errors="replace")
        for line in text.splitlines():
            m = line_re.match(line)
            if not m:
                continue
            hits = m.group(1).strip()
            if hits == "-" or hits == "=====":
                continue
            total_lines += 1
            if hits != "#####":
                covered_lines += 1
    return covered_lines, total_lines


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    run_gcov(root)
    covered, total = parse_gcov(root)
    if total == 0:
        print("No instrumented lines found. Did you build with coverage flags?")
        return 2

    pct = 100.0 * covered / total
    print(f"Coverage baseline: {covered}/{total} lines = {pct:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
