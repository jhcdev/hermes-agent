from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import tsr_video_annotation_tool.metadata as metadata_module
from tsr_video_annotation_tool import load_dataset_metadata, run_metadata_loading_check
from tsr_video_annotation_tool.metadata import (
    render_metadata_loading_report,
    write_metadata_loading_report_artifact,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PERF_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "perf" / "tsr_1000f_1080p"


def test_tsr_1000f_metadata_initial_load_completes_under_5_seconds() -> None:
    started = time.perf_counter()

    metadata = load_dataset_metadata(PERF_FIXTURE)

    elapsed_seconds = time.perf_counter() - started
    assert elapsed_seconds < 5.0
    assert metadata == {
        "fps": 30.0,
        "frame_height": 1080,
        "frame_path_template": "frames/frame_{frame_index:06d}.jpg",
        "frame_width": 1920,
        "schema_version": "tsr-dataset-metadata-v1",
        "total_frames": 1001,
        "video_id": "tsr_1000f_1080p",
    }


def test_metadata_loading_check_returns_stable_structured_output() -> None:
    result = run_metadata_loading_check(PERF_FIXTURE, threshold_seconds=5.0)

    assert result["ok"] is True
    assert result["status"] == "pass"
    assert result["schema_version"] == "tsr-metadata-load-check-v1"
    assert result["dataset_dir"] == str(PERF_FIXTURE)
    assert isinstance(result["elapsed_seconds"], float)
    assert 0 <= result["elapsed_seconds"] <= result["threshold_seconds"]
    assert result["threshold_seconds"] == 5.0
    assert result["dataset_size"] == {
        "frame_height": 1080,
        "frame_width": 1920,
        "total_frames": 1001,
    }
    assert result["summary"] == {
        "metadata_loaded": True,
        "threshold_passed": True,
        "total_frames": 1001,
    }
    assert result["metadata"]["total_frames"] == 1001
    assert result["error"] is None


def test_metadata_loading_check_reads_manifest_only_without_frame_payloads(
    tmp_path,
    monkeypatch,
) -> None:
    dataset_dir = tmp_path / "tsr_1000f_1080p_manifest_only"
    dataset_dir.mkdir()
    manifest_path = dataset_dir / "dataset.json"
    manifest_path.write_text(
        (PERF_FIXTURE / "dataset.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    opened_paths: list[Path] = []
    original_path_open = Path.open

    def record_manifest_only_open(self: Path, *args, **kwargs):
        opened_paths.append(self)
        if self != manifest_path:
            raise AssertionError(f"metadata loader materialized frame payload path: {self}")
        return original_path_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", record_manifest_only_open)

    result = run_metadata_loading_check(dataset_dir, threshold_seconds=5.0)

    assert result["ok"] is True
    assert result["metadata"] == {
        "fps": 30.0,
        "frame_height": 1080,
        "frame_path_template": "frames/frame_{frame_index:06d}.jpg",
        "frame_width": 1920,
        "schema_version": "tsr-dataset-metadata-v1",
        "total_frames": 1001,
        "video_id": "tsr_1000f_1080p",
    }
    assert result["dataset_size"] == {
        "frame_height": 1080,
        "frame_width": 1920,
        "total_frames": 1001,
    }
    assert opened_paths == [manifest_path]
    assert not (dataset_dir / "frames").exists()


def test_metadata_loading_check_records_when_load_exceeds_5_second_threshold(monkeypatch) -> None:
    def fake_load_dataset_metadata(dataset_dir: str | Path) -> dict[str, str | int | float]:
        assert Path(dataset_dir) == PERF_FIXTURE
        return {
            "fps": 30.0,
            "frame_height": 1080,
            "frame_path_template": "frames/frame_{frame_index:06d}.jpg",
            "frame_width": 1920,
            "schema_version": "tsr-dataset-metadata-v1",
            "total_frames": 1001,
            "video_id": "tsr_1000f_1080p",
        }

    timings = iter((10.0, 15.001))
    monkeypatch.setattr(metadata_module, "load_dataset_metadata", fake_load_dataset_metadata)
    monkeypatch.setattr(metadata_module.time, "perf_counter", lambda: next(timings))

    result = run_metadata_loading_check(PERF_FIXTURE, threshold_seconds=5.0)

    assert result["ok"] is False
    assert result["status"] == "fail"
    assert result["elapsed_seconds"] == 5.001
    assert result["threshold_seconds"] == 5.0
    assert result["summary"]["metadata_loaded"] is True
    assert result["summary"]["threshold_passed"] is False
    assert result["summary"]["total_frames"] == 1001
    assert result["error"] is None


def test_metadata_check_cli_invokes_loader_and_reports_threshold_status() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "metadata-check",
            "--dataset-dir",
            str(PERF_FIXTURE),
            "--threshold-seconds",
            "5",
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
    assert payload["schema_version"] == "tsr-metadata-load-check-v1"
    assert payload["dataset_size"]["total_frames"] == 1001
    assert isinstance(payload["elapsed_seconds"], float)
    assert 0 <= payload["elapsed_seconds"] <= payload["threshold_seconds"]
    assert payload["threshold_seconds"] == 5.0
    assert payload["summary"]["metadata_loaded"] is True
    assert payload["summary"]["threshold_passed"] is True
    assert payload["error"] is None
    assert payload["evidence_artifact"] == {
        "format": "json",
        "metadata_loaded": True,
        "path": None,
        "schema_version": "tsr-metadata-load-check-v1",
        "written": False,
    }


def test_metadata_check_cli_writes_metadata_loading_report_artifact(tmp_path) -> None:
    report_path = tmp_path / "reports" / "metadata-loading.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "metadata-check",
            "--dataset-dir",
            str(PERF_FIXTURE),
            "--threshold-seconds",
            "5",
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
    assert report_payload["status"] == "pass"
    assert report_payload["schema_version"] == "tsr-metadata-load-check-v1"
    assert report_payload["metadata"]["total_frames"] == 1001
    assert report_payload["summary"]["metadata_loaded"] is True
    assert report_payload["summary"]["threshold_passed"] is True
    assert report_payload["evidence_artifact"] == {
        "format": "json",
        "metadata_loaded": True,
        "path": str(report_path),
        "schema_version": "tsr-metadata-load-check-v1",
        "written": True,
    }


def test_metadata_loading_report_artifact_generation_is_reproducible_for_same_result(tmp_path) -> None:
    metadata_loading_result = run_metadata_loading_check(PERF_FIXTURE, threshold_seconds=5.0)
    first_report_path = tmp_path / "first-metadata-loading.json"
    second_report_path = tmp_path / "second-metadata-loading.json"

    write_metadata_loading_report_artifact(first_report_path, metadata_loading_result)
    write_metadata_loading_report_artifact(second_report_path, metadata_loading_result)

    expected_content = render_metadata_loading_report(metadata_loading_result).encode("utf-8")
    assert first_report_path.read_bytes() == expected_content
    assert second_report_path.read_bytes() == expected_content
    assert first_report_path.read_bytes() == second_report_path.read_bytes()
