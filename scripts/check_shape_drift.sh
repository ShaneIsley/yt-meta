#!/usr/bin/env bash
#
# check_shape_drift.sh — run the live structural contract suite to detect
# whether YouTube has changed a response shape our parsers depend on.
#
# WHY: yt-meta parses YouTube's undocumented internal JSON, whose shape
# changes without notice (e.g. the videoRenderer -> lockupViewModel
# migration that silently zeroed out get_channel_videos / get_playlist_videos).
# The contract suite hits LIVE YouTube and asserts only the *structure* our
# parsers rely on — types, key presence, that documented capabilities still
# return data — never volatile values. A failure here means "investigate the
# parser", not "flaky network".
#
# This CANNOT run in GitHub Actions — YouTube blocks GHA runners — so run it
# locally before a release, or on a schedule from a machine with normal
# YouTube access.
#
# USAGE:
#   ./scripts/check_shape_drift.sh                 # run all contract tests
#   ./scripts/check_shape_drift.sh -k playlist     # filter (pytest args pass through)
#   make drift                                     # via the Makefile
#
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> yt-meta live shape-drift check (pytest -m contract)"
echo "    Hits LIVE YouTube. A failure = a likely parser/shape break, not a flake."
echo

set +e
uv run pytest -m contract -v "$@"
status=$?
set -e

echo
if [ "$status" -eq 0 ]; then
    echo "==> OK: every capability still matches YouTube's current shape."
else
    echo "==> DRIFT DETECTED (exit $status): a contract assertion failed."
    echo "    Before assuming a network flake: re-run the single failing test,"
    echo "    then probe the live page for the affected parser — this is the"
    echo "    signature of a YouTube structure change (cf. lockupViewModel)."
fi
exit "$status"
