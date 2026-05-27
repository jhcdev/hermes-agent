from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_launch_check_cli_entry_point_returns_pass_result():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.launch_check",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["ok"] is True
    assert payload["status"] == "pass"
    assert payload["schema_version"] == "tsr-launch-check-v1"
    assert payload["checks"]["public_contract"]["schema_version"] == "tsr-public-contract-check-v1"
    assert payload["summary"]["checks"] == {
        "browser_bundle": "pass",
        "public_contract": "pass",
        "quit_path": "pass",
    }
    assert payload["summary"]["failed_checks"] == []
    assert payload["summary"]["overall"] == "pass"
    assert payload["checks"]["public_contract"]["ok"] is True
    assert payload["checks"]["browser_bundle"]["ok"] is True
    assert payload["checks"]["quit_path"]["ok"] is True
    assert payload["checks"]["quit_path"]["termination_path"] == "normal"
    assert payload["checks"]["quit_path"]["quit_signal_received"] is True
    assert payload["checks"]["quit_path"]["elapsed_ms"] < 2000
    assert payload["evidence_artifact"]["written"] is False
    assert payload["evidence_artifact"]["path"] is None
    assert payload["evidence_artifact"]["launch_check_passed"] is True


def test_launch_check_cli_entry_point_returns_fail_result():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.launch_check",
            "--module",
            "tsr_video_annotation_tool.missing_module",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["ok"] is False
    assert payload["status"] == "fail"
    assert payload["schema_version"] == "tsr-launch-check-v1"
    assert payload["summary"]["checks"] == {
        "browser_bundle": "pass",
        "public_contract": "fail",
        "quit_path": "pass",
    }
    assert "public_contract" in payload["summary"]["failed_checks"]
    assert payload["summary"]["overall"] == "fail"
    assert payload["checks"]["public_contract"]["summary"]["modules_failed"] == 1


def test_launch_check_cli_writes_independently_verifiable_report_artifact(tmp_path):
    report_path = tmp_path / "evidence" / "launch-check.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.launch_check",
            "--report-path",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    stdout_payload = json.loads(completed.stdout)
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert report_path.is_file()
    assert report_payload == stdout_payload
    assert report_payload["ok"] is True
    assert report_payload["schema_version"] == "tsr-launch-check-v1"
    assert report_payload["evidence_artifact"] == {
        "format": "json",
        "launch_check_passed": True,
        "path": str(report_path),
        "schema_version": "tsr-launch-check-v1",
        "written": True,
    }


def test_tsr_annotate_launch_check_subcommand_uses_same_contract():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "launch-check",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["ok"] is True
    assert payload["schema_version"] == "tsr-launch-check-v1"
    assert set(payload["checks"]) == {"browser_bundle", "public_contract", "quit_path"}
    assert payload["checks"]["quit_path"]["ok"] is True


def test_tsr_annotate_launch_check_subcommand_writes_report_artifact(tmp_path):
    report_path = tmp_path / "launch-check-report.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "launch-check",
            "--report-path",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    stdout_payload = json.loads(completed.stdout)
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert report_payload == stdout_payload
    assert report_payload["evidence_artifact"]["path"] == str(report_path)
    assert report_payload["evidence_artifact"]["written"] is True
    assert report_payload["evidence_artifact"]["launch_check_passed"] is True


def test_report_artifact_pass_status_is_independently_validatable(tmp_path):
    report_path = tmp_path / "launch-check.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.launch_check",
            "--report-path",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert completed.returncode == 0
    artifact = json.loads(report_path.read_text(encoding="utf-8"))
    assert artifact["evidence_artifact"]["path"] == str(report_path)
    assert artifact["evidence_artifact"]["written"] is True
    assert artifact["evidence_artifact"]["launch_check_passed"] is True
    assert artifact["ok"] is artifact["evidence_artifact"]["launch_check_passed"]
    assert artifact["status"] == "pass"
    assert artifact["summary"]["checks"] == {
        "browser_bundle": "pass",
        "public_contract": "pass",
        "quit_path": "pass",
    }
    assert artifact["summary"]["failed_checks"] == []
    assert artifact["summary"]["overall"] == "pass"


def test_packaged_console_script_metadata_exposes_launch_check_entry_point():
    project_metadata = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project_metadata["project"]["scripts"]["tsr-launch-check"] == (
        "tsr_video_annotation_tool.launch_check:main"
    )


def test_tsr_annotate_main_loop_quit_signal_reaches_normal_termination_path():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "run-loop",
        ],
        input="quit\n",
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload == {
        "ignored_commands": [],
        "ok": True,
        "processed_commands": 1,
        "quit_signal_received": True,
        "schema_version": "tsr-main-loop-v1",
        "status": "terminated",
        "termination_path": "normal",
    }


def test_launch_check_quit_path_completes_within_bounded_timeout():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "launch-check",
            "--quit-timeout-seconds",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        cwd=REPO_ROOT,
    )

    payload = json.loads(completed.stdout)
    quit_path = payload["checks"]["quit_path"]
    assert completed.returncode == 0
    assert payload["summary"]["checks"]["quit_path"] == "pass"
    assert quit_path["ok"] is True
    assert quit_path["timeout_seconds"] == 2.0
    assert quit_path["elapsed_ms"] < 2000
    assert quit_path["termination_path"] == "normal"
    assert quit_path["quit_signal_received"] is True
    assert quit_path["error"] is None
