"""Smoke-test the PUBLISHED PyPI package (marker: pypi; excluded by default).

The offline and contract suites run against the editable local checkout, so
they cannot catch packaging bugs — a module missing from the wheel, a wrong
dependency pin, or a fix that never made it into the uploaded distribution.

This delegates to ``scripts/smoke_pypi.sh``, which installs yt-meta FROM PyPI
into a throwaway venv and exercises the core + playlist paths against live
YouTube. It pins to this repo's current ``__version__``, so it also asserts
that exact version is live on PyPI and healthy.

Run deliberately (installs from PyPI + hits live YouTube; not CI-able)::

    pytest -m pypi
    make smoke-pypi
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pypi

SCRIPT = Path(__file__).parent.parent / "scripts" / "smoke_pypi.sh"


def test_published_pypi_package_smoke():
    if shutil.which("uv") is None:
        pytest.skip("uv is required to build the isolated venv")
    assert SCRIPT.exists(), f"missing smoke script: {SCRIPT}"

    import yt_meta

    version = yt_meta.__version__
    result = subprocess.run(
        ["bash", str(SCRIPT), version],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"PyPI smoke test failed for yt-meta=={version}:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
