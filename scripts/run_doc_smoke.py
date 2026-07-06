#!/usr/bin/env python
"""Run every README code block and every example script against live YouTube.

The offline suite proves the library; this proves the documentation.
Each ```python``` block in README.md and each script under examples/ runs
in an isolated subprocess with a timeout. Anything that exits non-zero
fails the run.

Hits live YouTube (sequentially, with a short delay between items), so it
cannot run in CI. Run it before a release:

    uv run --with diskcache python scripts/run_doc_smoke.py
    uv run --with diskcache python scripts/run_doc_smoke.py --only readme
    uv run --with diskcache python scripts/run_doc_smoke.py --only examples

The diskcache extra is needed by the persistent-caching README block.
"""

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 120
DELAY = 1.0


def readme_blocks():
    text = (ROOT / "README.md").read_text()
    for i, match in enumerate(re.finditer(r"```python\n(.*?)```", text, re.DOTALL), 1):
        line = text[: match.start()].count("\n") + 1
        yield f"README block {i} (line {line})", match.group(1)


def example_scripts():
    for pattern in ("examples/*.py", "examples/features/*.py"):
        yield from sorted(ROOT.glob(pattern))


def run_source(name, source, cwd):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(source)
        path = f.name
    return run_file(name, Path(path), cwd)


def run_file(name, path, cwd):
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        ok = proc.returncode == 0
        detail = "" if ok else (proc.stderr or proc.stdout).strip().splitlines()[-1:]
    except subprocess.TimeoutExpired:
        ok, detail = False, [f"timeout after {TIMEOUT}s"]
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f"  -> {detail[0]}" if detail else ""), flush=True)
    time.sleep(DELAY)
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["readme", "examples"])
    args = parser.parse_args()

    results = []
    if args.only in (None, "readme"):
        for name, source in readme_blocks():
            results.append(run_source(name, source, cwd=ROOT))
    if args.only in (None, "examples"):
        for path in example_scripts():
            results.append(run_file(str(path.relative_to(ROOT)), path, cwd=ROOT))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
