from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from queue import Empty
from typing import Any

from tsr_video_annotation_tool.main_loop import run_annotation_main_loop
from tsr_video_annotation_tool.public_contract import run_public_contract_check
from tsr_video_annotation_tool.web import get_browser_bundle_root

LAUNCH_CHECK_SCHEMA_VERSION = "tsr-launch-check-v1"
DEFAULT_QUIT_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class BrowserBundleCheck:
    root: str
    index_html: str
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class QuitPathCheck:
    ok: bool
    timeout_seconds: float
    elapsed_ms: float
    termination_path: str | None = None
    quit_signal_received: bool | None = None
    error: str | None = None


def run_launch_check(
    *,
    modules: tuple[str, ...] | list[str] | None = None,
    symbols: tuple[str, ...] | list[str] | None = None,
    report_path: str | Path | None = None,
    quit_timeout_seconds: float = DEFAULT_QUIT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return a JSON-serializable pass/fail launch readiness report."""

    public_contract = run_public_contract_check(modules=modules, symbols=symbols)
    browser_bundle = _check_browser_bundle()
    quit_path = run_quit_path_check(timeout_seconds=quit_timeout_seconds)
    check_results = {
        "public_contract": bool(public_contract["ok"]),
        "browser_bundle": browser_bundle.ok,
        "quit_path": quit_path.ok,
    }
    ok = all(check_results.values())
    normalized_report_path = str(Path(report_path)) if report_path is not None else None

    result = {
        "ok": ok,
        "status": _status_for(ok),
        "schema_version": LAUNCH_CHECK_SCHEMA_VERSION,
        "checks": {
            "public_contract": public_contract,
            "browser_bundle": asdict(browser_bundle),
            "quit_path": asdict(quit_path),
        },
        "summary": {
            "checks": {name: _status_for(check_ok) for name, check_ok in check_results.items()},
            "failed_checks": [name for name, check_ok in check_results.items() if not check_ok],
            "overall": _status_for(ok),
        },
        "evidence_artifact": {
            "format": "json",
            "launch_check_passed": ok,
            "path": normalized_report_path,
            "schema_version": LAUNCH_CHECK_SCHEMA_VERSION,
            "written": report_path is not None,
        },
    }

    if report_path is not None:
        _write_report_artifact(Path(report_path), result)

    return result


def run_quit_path_check(timeout_seconds: float = DEFAULT_QUIT_TIMEOUT_SECONDS) -> QuitPathCheck:
    """Verify the annotation loop exits on quit within a bounded timeout."""

    if timeout_seconds <= 0:
        return QuitPathCheck(
            ok=False,
            timeout_seconds=timeout_seconds,
            elapsed_ms=0.0,
            error="timeout_seconds must be positive",
        )

    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(target=_run_quit_path_worker, args=(result_queue,))
    start = time.monotonic()
    process.start()
    process.join(timeout_seconds)
    elapsed_ms = round((time.monotonic() - start) * 1000, 3)

    if process.is_alive():
        process.terminate()
        process.join(1)
        return QuitPathCheck(
            ok=False,
            timeout_seconds=timeout_seconds,
            elapsed_ms=elapsed_ms,
            error="quit path timed out",
        )

    if process.exitcode != 0:
        return QuitPathCheck(
            ok=False,
            timeout_seconds=timeout_seconds,
            elapsed_ms=elapsed_ms,
            error=f"worker exited with code {process.exitcode}",
        )

    try:
        payload = result_queue.get(timeout=0.25)
    except Empty:
        return QuitPathCheck(
            ok=False,
            timeout_seconds=timeout_seconds,
            elapsed_ms=elapsed_ms,
            error="worker did not return a result",
        )

    if not isinstance(payload, dict):
        return QuitPathCheck(
            ok=False,
            timeout_seconds=timeout_seconds,
            elapsed_ms=elapsed_ms,
            error="worker returned a non-object result",
        )

    ok = (
        payload.get("ok") is True
        and payload.get("termination_path") == "normal"
        and payload.get("quit_signal_received") is True
    )
    return QuitPathCheck(
        ok=ok,
        timeout_seconds=timeout_seconds,
        elapsed_ms=elapsed_ms,
        termination_path=_as_optional_string(payload.get("termination_path")),
        quit_signal_received=(
            payload.get("quit_signal_received")
            if isinstance(payload.get("quit_signal_received"), bool)
            else None
        ),
        error=None if ok else "quit command did not reach the normal termination path",
    )


def _status_for(ok: bool) -> str:
    return "pass" if ok else "fail"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tsr-launch-check")
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Module import path to check; may be repeated. Defaults to documented public modules.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Public symbol as MODULE:SYMBOL; may be repeated. Defaults to documented public symbols.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Write the launch readiness JSON report to this path for external verification.",
    )
    parser.add_argument(
        "--quit-timeout-seconds",
        type=float,
        default=DEFAULT_QUIT_TIMEOUT_SECONDS,
        help="Maximum seconds allowed for the quit-path launch check.",
    )
    args = parser.parse_args(argv)

    result = run_launch_check(
        modules=args.modules,
        symbols=args.symbols,
        report_path=args.report_path,
        quit_timeout_seconds=args.quit_timeout_seconds,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


def _check_browser_bundle() -> BrowserBundleCheck:
    try:
        bundle_root = get_browser_bundle_root()
        index_html = bundle_root / "index.html"
        if not index_html.is_file():
            return BrowserBundleCheck(
                root=str(bundle_root),
                index_html=str(index_html),
                ok=False,
                error="index.html is missing",
            )
        if index_html.stat().st_size == 0:
            return BrowserBundleCheck(
                root=str(bundle_root),
                index_html=str(index_html),
                ok=False,
                error="index.html is empty",
            )
        return BrowserBundleCheck(root=str(bundle_root), index_html=str(index_html), ok=True)
    except Exception as exc:
        root = _best_effort_bundle_root()
        return BrowserBundleCheck(
            root=str(root),
            index_html=str(root / "index.html"),
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def _best_effort_bundle_root() -> Path:
    try:
        return get_browser_bundle_root()
    except Exception:
        return Path("tsr_video_annotation_tool") / "web_dist"


def _write_report_artifact(report_path: Path, payload: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = report_path.with_name(f".{report_path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, report_path)


def _run_quit_path_worker(queue: multiprocessing.Queue) -> None:
    queue.put(run_annotation_main_loop(["quit\n"]))


def _as_optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


if __name__ == "__main__":
    raise SystemExit(main())
