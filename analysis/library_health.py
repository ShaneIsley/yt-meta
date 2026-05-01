"""Library health & test analysis notebook for yt-meta.

Run with:    uv run marimo edit analysis/library_health.py
Or read-only: uv run marimo run  analysis/library_health.py
"""

import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md("""
    # yt-meta — Library Health Report

    A reactive analysis of test results, lint findings, network reachability,
    and known live defects for the **yt-meta** library.

    - Test runner: `pytest` with JUnit XML output
    - Lint: `ruff check`
    - Live probe: direct `httpx` calls to YouTube + a control host
    - Issues: GitHub issue tracker for `shaneisley/yt-meta`
    """)
    return


@app.cell
def _(mo):
    rerun = mo.ui.button(label="Re-run test suite", kind="success")
    rerun
    return (rerun,)


@app.cell
def _():
    import json
    import re
    import subprocess
    import xml.etree.ElementTree as ET
    from pathlib import Path

    import pandas as pd
    import plotly.express as px

    REPO = Path(__file__).resolve().parent.parent
    XML_PATH = REPO / "analysis" / "_pytest_results.xml"
    return ET, REPO, XML_PATH, pd, px, re, subprocess


@app.cell
def _(REPO, XML_PATH, rerun, subprocess):
    rerun  # reactive trigger
    proc = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            f"--junit-xml={XML_PATH}",
            "--tb=line",
            "-q",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )
    pytest_stdout = proc.stdout + "\n" + proc.stderr
    pytest_returncode = proc.returncode
    return (pytest_returncode,)


@app.cell
def _(ET, XML_PATH, pd, pytest_returncode, re):
    _ = pytest_returncode  # depend on pytest cell
    tree = ET.parse(XML_PATH)
    suite = tree.getroot().find("testsuite")
    suite_attrs = {
        "tests": int(suite.get("tests", 0)),
        "failures": int(suite.get("failures", 0)),
        "errors": int(suite.get("errors", 0)),
        "skipped": int(suite.get("skipped", 0)),
        "time": float(suite.get("time", 0.0)),
    }

    rows = []
    for case in suite.findall("testcase"):
        classname = case.get("classname", "")
        module = classname.split(".")[0] if classname else ""
        name = case.get("name", "")
        case_duration = float(case.get("time", 0.0))
        outcome = "passed"
        message = ""
        failure_node = case.find("failure")
        error_node = case.find("error")
        skipped_node = case.find("skipped")
        if failure_node is not None:
            outcome = "failed"
            message = failure_node.get("message", "") or (failure_node.text or "")
        elif error_node is not None:
            outcome = "error"
            message = error_node.get("message", "") or (error_node.text or "")
        elif skipped_node is not None:
            outcome = "skipped"
            message = skipped_node.get("message", "") or (skipped_node.text or "")

        is_integration = "integration" in name.lower() or "_live" in name.lower()
        rows.append(
            {
                "module": module,
                "test": name,
                "outcome": outcome,
                "duration_s": case_duration,
                "kind": "integration" if is_integration else "unit",
                "message": (message or "").strip().splitlines()[0][:240]
                if message
                else "",
            }
        )

    tests_df = pd.DataFrame(rows)

    failure_re = re.compile(r"403|forbidden|HTTPStatus|ConnectError|ConnectTimeout", re.I)
    sandbox_re = re.compile(r"403", re.I)

    def classify(msg: str) -> str:
        if not msg:
            return "—"
        if "Host not in allowlist" in msg or "host_not_allowed" in msg:
            return "sandbox-blocked"
        if sandbox_re.search(msg):
            return "http-403"
        if "transcript" in msg.lower():
            return "transcript-empty"
        if failure_re.search(msg):
            return "network"
        return "other"

    tests_df["failure_kind"] = tests_df["message"].map(classify)
    return suite_attrs, tests_df


@app.cell
def _(mo, suite_attrs, tests_df):
    total = suite_attrs["tests"]
    passed = int((tests_df["outcome"] == "passed").sum())
    failed = int((tests_df["outcome"].isin(["failed", "error"])).sum())
    skipped = int((tests_df["outcome"] == "skipped").sum())
    total_duration = suite_attrs["time"]
    pass_rate = (passed / total * 100) if total else 0.0

    mo.hstack(
        [
            mo.stat(label="Total tests", value=str(total), bordered=True),
            mo.stat(
                label="Passed",
                value=str(passed),
                caption=f"{pass_rate:.1f}% pass rate",
                direction="increase" if pass_rate > 80 else "decrease",
                bordered=True,
            ),
            mo.stat(
                label="Failed / errored",
                value=str(failed),
                direction="decrease" if failed else "increase",
                bordered=True,
            ),
            mo.stat(label="Skipped", value=str(skipped), bordered=True),
            mo.stat(
                label="Duration",
                value=f"{total_duration:.2f}s",
                bordered=True,
            ),
        ],
        justify="space-between",
        gap=1,
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Outcome distribution
    """)
    return


@app.cell
def _(px, tests_df):
    outcome_counts = (
        tests_df.groupby(["kind", "outcome"]).size().reset_index(name="count")
    )
    fig_outcome = px.sunburst(
        outcome_counts,
        path=["kind", "outcome"],
        values="count",
        color="outcome",
        color_discrete_map={
            "passed": "#16a34a",
            "failed": "#dc2626",
            "error": "#7c2d12",
            "skipped": "#f59e0b",
        },
        title="Outcomes split by unit vs integration",
    )
    fig_outcome.update_layout(height=420, margin=dict(t=50, l=10, r=10, b=10))
    fig_outcome
    return


@app.cell
def _(mo):
    mo.md("""
    ## Per-module breakdown
    """)
    return


@app.cell
def _(px, tests_df):
    by_module = (
        tests_df.groupby(["module", "outcome"]).size().reset_index(name="count")
    )
    fig_module = px.bar(
        by_module,
        x="module",
        y="count",
        color="outcome",
        barmode="stack",
        color_discrete_map={
            "passed": "#16a34a",
            "failed": "#dc2626",
            "error": "#7c2d12",
            "skipped": "#f59e0b",
        },
        title="Test outcomes by test module",
    )
    fig_module.update_layout(height=420, xaxis_tickangle=-30)
    fig_module
    return


@app.cell
def _(mo):
    mo.md("""
    ## Test duration profile
    """)
    return


@app.cell
def _(px, tests_df):
    fig_time = px.histogram(
        tests_df,
        x="duration_s",
        color="outcome",
        nbins=40,
        marginal="rug",
        color_discrete_map={
            "passed": "#16a34a",
            "failed": "#dc2626",
            "error": "#7c2d12",
            "skipped": "#f59e0b",
        },
        title="Per-test duration (seconds)",
        labels={"duration_s": "duration (s)"},
    )
    fig_time.update_layout(height=380)
    fig_time
    return


@app.cell
def _(mo):
    mo.md("""
    ## Failure classification

    Failures are bucketed so we can tell **environmental** issues
    (sandbox firewall blocking YouTube) apart from **library** issues.
    In this run, every "failure" should fall into the `sandbox-blocked` /
    `http-403` bucket — those tests need real internet egress to pass.
    """)
    return


@app.cell
def _(px, tests_df):
    fail_only = tests_df[tests_df["outcome"].isin(["failed", "error"])].copy()
    if fail_only.empty:
        fig_fail = px.bar(title="No failures 🎉")
    else:
        cnt = fail_only.groupby("failure_kind").size().reset_index(name="count")
        fig_fail = px.bar(
            cnt,
            x="failure_kind",
            y="count",
            color="failure_kind",
            title="Failures grouped by detected cause",
        )
    fig_fail.update_layout(height=320, showlegend=False)
    fig_fail
    return (fail_only,)


@app.cell
def _(fail_only, mo):
    if fail_only.empty:
        out = mo.md("**No failed tests.**")
    else:
        out = mo.ui.table(
            fail_only[["module", "test", "kind", "failure_kind", "message"]]
            .sort_values(["failure_kind", "module", "test"])
            .reset_index(drop=True),
            label="Failed tests (one row per failure)",
            page_size=25,
        )
    out
    return


@app.cell
def _(mo):
    mo.md("""
    ## Lint (`ruff check yt_meta/`)
    """)
    return


@app.cell
def _(REPO, pd, subprocess):
    ruff_proc = subprocess.run(
        ["uv", "run", "ruff", "check", "yt_meta/", "--output-format=json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    import json as _json

    try:
        ruff_findings = _json.loads(ruff_proc.stdout or "[]")
    except _json.JSONDecodeError:
        ruff_findings = []

    if ruff_findings:
        ruff_rows = [
            {
                "file": str(f.get("filename", "")).replace(str(REPO) + "/", ""),
                "code": f.get("code"),
                "message": f.get("message"),
                "line": (f.get("location") or {}).get("row"),
                "fixable": bool(f.get("fix")),
            }
            for f in ruff_findings
        ]
        ruff_df = pd.DataFrame(ruff_rows)
    else:
        ruff_df = pd.DataFrame(columns=["file", "code", "message", "line", "fixable"])
    return (ruff_df,)


@app.cell
def _(mo, px, ruff_df):
    if ruff_df.empty:
        view = mo.md("✅ **No lint findings**")
    else:
        by_code = ruff_df.groupby("code").size().reset_index(name="count")
        lint_chart = px.bar(
            by_code.sort_values("count", ascending=True),
            x="count",
            y="code",
            orientation="h",
            title=f"Ruff findings by rule  ({len(ruff_df)} total, "
            f"{int(ruff_df['fixable'].sum())} auto-fixable)",
        )
        lint_chart.update_layout(height=300, margin=dict(t=50, l=10, r=10, b=10))
        view = mo.vstack(
            [
                lint_chart,
                mo.ui.table(
                    ruff_df.sort_values(["code", "file", "line"]).reset_index(drop=True),
                    label="Lint findings",
                    page_size=20,
                ),
            ]
        )
    view
    return


@app.cell
def _(mo):
    mo.md("""
    ## Network reachability probe

    Integration tests need to reach `youtube.com`. This cell hits a few hosts
    directly so we can tell whether failures upstream are caused by YouTube or
    by the local environment (e.g. sandbox firewall).
    """)
    return


@app.cell
def _(pd):
    import httpx

    PROBES = [
        ("YouTube watch page", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("YouTube channel", "https://www.youtube.com/@TED/videos"),
        ("YouTube consent", "https://consent.youtube.com/"),
        ("httpbin (control)", "https://httpbin.org/get"),
        ("example.com (control)", "https://example.com/"),
    ]
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    probe_rows = []
    for label, url in PROBES:
        try:
            r = httpx.get(
                url,
                headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.5"},
                follow_redirects=True,
                timeout=8.0,
            )
            probe_rows.append(
                {
                    "target": label,
                    "url": url,
                    "status": r.status_code,
                    "final_url": str(r.url)[:80],
                    "deny_reason": r.headers.get("x-deny-reason", ""),
                    "bytes": len(r.content),
                    "ok": r.status_code < 400,
                }
            )
        except Exception as exc:
            probe_rows.append(
                {
                    "target": label,
                    "url": url,
                    "status": None,
                    "final_url": "",
                    "deny_reason": type(exc).__name__,
                    "bytes": 0,
                    "ok": False,
                }
            )
    probe_df = pd.DataFrame(probe_rows)
    return (probe_df,)


@app.cell
def _(mo, probe_df, px):
    probe_chart = px.bar(
        probe_df,
        x="target",
        y="bytes",
        color="ok",
        hover_data=["status", "final_url", "deny_reason"],
        color_discrete_map={True: "#16a34a", False: "#dc2626"},
        title="Bytes returned per probe target",
    )
    probe_chart.update_layout(height=320, xaxis_tickangle=-15)
    mo.vstack(
        [
            probe_chart,
            mo.ui.table(probe_df, page_size=10, label="Probe responses"),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Known live defect — Issue #1

    > Fetching videos of channel fails due to cookie accept pop-up
    > — `gh:shaneisley/yt-meta#1`

    **Symptom (from issue):**

    ```text
    httpx.HTTPStatusError: Redirect response '302 Found' for url
        'https://www.youtube.com/@minkispacebirb/videos'
    Redirect location:
        'https://consent.youtube.com/m?continue=...&gl=DE&m=0&pc=yt&cm=2&hl=en&src=1'
    ```

    **Root cause** — `yt_meta/client.py:33` constructs the shared `httpx.Client`
    without `follow_redirects=True`, without a real `User-Agent`, and without a
    consent cookie (`SOCS=CAI`). Every EU/UK request bounces to `consent.youtube.com`
    and `raise_for_status()` at `yt_meta/fetchers.py:183` rewraps it as
    `VideoUnavailableError`.

    **All vulnerable call sites share the same session**:

    | File | Line | Method |
    | --- | --- | --- |
    | `yt_meta/fetchers.py` | 116 | `VideoFetcher.get_video_metadata` |
    | `yt_meta/fetchers.py` | 183 | `ChannelFetcher._get_channel_page_data` |
    | `yt_meta/fetchers.py` | 215 | `ChannelFetcher._get_channel_shorts_page_data` |
    | `yt_meta/fetchers.py` | 521 | `PlaylistFetcher._get_raw_playlist_videos_generator` |

    Fixing the session at `client.py:33` covers all of them in one change.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Codebase metrics
    """)
    return


@app.cell
def _(REPO, pd):
    src_dir = REPO / "yt_meta"
    file_rows = []
    for path in sorted(src_dir.rglob("*.py")):
        try:
            text = path.read_text()
        except Exception:
            continue
        loc = sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))
        file_rows.append(
            {
                "file": str(path.relative_to(REPO)),
                "lines": len(text.splitlines()),
                "loc": loc,
                "size_kb": round(path.stat().st_size / 1024, 1),
            }
        )
    src_df = pd.DataFrame(file_rows).sort_values("loc", ascending=False)
    return (src_df,)


@app.cell
def _(px, src_df):
    loc_chart = px.bar(
        src_df,
        x="loc",
        y="file",
        orientation="h",
        title=f"Lines of code per source file (total LOC: {int(src_df['loc'].sum())})",
        hover_data=["lines", "size_kb"],
    )
    loc_chart.update_layout(
        height=max(320, 22 * len(src_df)),
        margin=dict(t=50, l=10, r=10, b=10),
        yaxis={"categoryorder": "total ascending"},
    )
    loc_chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## Verdict

    - **Unit health: green.** All non-network tests pass. Module structure is
      clean (`VideoFetcher` / `ChannelFetcher` / `PlaylistFetcher` /
      `CommentFetcher` / `TranscriptFetcher` behind a `YtMeta` facade).
    - **Integration health: not verifiable from this sandbox.** All upstream
      probes return `403 / x-deny-reason: host_not_allowed`. Failures here
      are environmental, not regressions.
    - **Live defect known and triaged**: Issue #1 (consent redirect) is real
      for EU/UK users. One-line fix at `yt_meta/client.py:33`
      (add `follow_redirects=True`, real User-Agent, `SOCS=CAI` cookie).
    - **Style nits**: a handful of ruff findings, mostly auto-fixable.

    Re-run this notebook from a host with unrestricted egress to confirm
    live behaviour and to validate Issue #1's fix end-to-end.
    """)
    return


if __name__ == "__main__":
    app.run()
