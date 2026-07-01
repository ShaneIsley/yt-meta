#!/usr/bin/env bash
#
# smoke_pypi.sh — install yt-meta FROM PYPI into a throwaway venv and smoke-test
# the *published* artifact, independent of the local source tree.
#
# WHY: the offline/contract suites run against the editable local checkout, so
# they can't catch packaging bugs — a module left out of the wheel, a wrong or
# missing dependency pin, or a fix that never made it into the uploaded
# distribution. This installs the real published package into an isolated venv
# and exercises the core + playlist paths against live YouTube.
#
# It hits live YouTube and installs from PyPI, so — like the contract suite —
# it CANNOT run in GitHub Actions (YouTube blocks GHA runners). Run it locally
# right after `uv publish` to confirm the upload is sound.
#
# USAGE:
#   ./scripts/smoke_pypi.sh            # test the latest version on PyPI
#   ./scripts/smoke_pypi.sh 0.7.1      # pin and verify a specific version
#   make smoke-pypi                    # via the Makefile
#
set -euo pipefail

VERSION="${1:-}"
SPEC="yt-meta${VERSION:+==$VERSION}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
venv="$workdir/venv"

echo "==> smoke-testing PyPI package: ${SPEC}"
echo "    (isolated venv, installed from PyPI — NOT the local source tree)"
echo

uv venv "$venv" >/dev/null
# Resolve deps and install ONLY from PyPI into the throwaway venv.
uv pip install --python "$venv/bin/python" --quiet "$SPEC"

"$venv/bin/python" - "$VERSION" <<'PY'
import itertools
import sys

import yt_meta
from yt_meta import YtMeta

expected = sys.argv[1] or None
print(f"installed: yt_meta {yt_meta.__version__}")
if expected and yt_meta.__version__ != expected:
    sys.exit(f"FAIL: expected {expected}, got {yt_meta.__version__}")

client = YtMeta()
try:
    # 1) Core single-video path (also proves the dep closure imports).
    meta = client.get_video_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert meta and meta["title"] == "Me at the zoo", (
        f"video metadata broke: {meta and meta.get('title')!r}"
    )

    # 2) Playlist path — the 0.7.1 lockupViewModel fix MUST be in the shipped
    #    wheel. If the published package predates the fix, this returns [].
    vids = list(
        itertools.islice(
            client.get_playlist_videos("PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU"), 3
        )
    )
    assert vids, (
        "get_playlist_videos returned 0 — the lockupViewModel fix is NOT in "
        "the published package"
    )
    assert all(len(v["video_id"]) == 11 for v in vids), "malformed video ids"
finally:
    client.close()

print("OK: published package imports and core + playlist paths work")
PY

echo
echo "==> PyPI smoke test passed for ${SPEC}"
