from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DATASET_MANIFEST = "dataset.json"
METADATA_SCHEMA_VERSION = "tsr-dataset-metadata-v1"
METADATA_LOAD_CHECK_SCHEMA_VERSION = "tsr-metadata-load-check-v1"
DEFAULT_METADATA_LOAD_THRESHOLD_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class DatasetMetadata:
    """Frame dataset metadata loaded without touching frame image payloads."""

    video_id: str
    total_frames: int
    frame_width: int
    frame_height: int
    fps: float
    frame_path_template: str
    schema_version: str = METADATA_SCHEMA_VERSION

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


def load_dataset_metadata(dataset_dir: str | Path) -> dict[str, str | int | float]:
    """Load initial video dataset metadata from a small manifest file.

    The loader intentionally reads only ``dataset.json``. Large frame payloads,
    thumbnails, and annotation streams are left untouched so startup time stays
    bounded for 1000+ frame datasets.
    """

    manifest_path = Path(dataset_dir) / DATASET_MANIFEST
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    metadata = DatasetMetadata(
        video_id=_validate_text("video_id", manifest.get("video_id")),
        total_frames=_validate_positive_int("total_frames", manifest.get("total_frames")),
        frame_width=_validate_positive_int("frame_width", manifest.get("frame_width")),
        frame_height=_validate_positive_int("frame_height", manifest.get("frame_height")),
        fps=_validate_positive_number("fps", manifest.get("fps")),
        frame_path_template=_validate_text("frame_path_template", manifest.get("frame_path_template")),
    )
    return metadata.to_dict()


def run_metadata_loading_check(
    dataset_dir: str | Path,
    *,
    threshold_seconds: float = DEFAULT_METADATA_LOAD_THRESHOLD_SECONDS,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load dataset metadata and return a structured pass/fail readiness check."""

    started = time.perf_counter()
    metadata: dict[str, str | int | float] | None = None
    error: str | None = None
    try:
        metadata = load_dataset_metadata(dataset_dir)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    elapsed_seconds = round(time.perf_counter() - started, 6)
    threshold_ok = threshold_seconds > 0
    ok = metadata is not None and error is None and threshold_ok and elapsed_seconds <= threshold_seconds
    dataset_size = _dataset_size_from_metadata(metadata)

    normalized_report_path = str(Path(report_path)) if report_path is not None else None

    result = {
        "ok": ok,
        "status": "pass" if ok else "fail",
        "schema_version": METADATA_LOAD_CHECK_SCHEMA_VERSION,
        "dataset_dir": str(Path(dataset_dir)),
        "elapsed_seconds": elapsed_seconds,
        "threshold_seconds": float(threshold_seconds),
        "dataset_size": dataset_size,
        "metadata": metadata,
        "summary": {
            "metadata_loaded": metadata is not None,
            "threshold_passed": elapsed_seconds <= threshold_seconds if threshold_ok else False,
            "total_frames": dataset_size["total_frames"] if dataset_size is not None else None,
        },
        "error": error if threshold_ok else "threshold_seconds must be positive",
        "evidence_artifact": {
            "format": "json",
            "metadata_loaded": metadata is not None,
            "path": normalized_report_path,
            "schema_version": METADATA_LOAD_CHECK_SCHEMA_VERSION,
            "written": report_path is not None,
        },
    }

    if report_path is not None:
        write_metadata_loading_report_artifact(report_path, result)

    return result


def render_metadata_loading_report(payload: dict[str, Any]) -> str:
    """Return the canonical JSON report content for a metadata loading result."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def write_metadata_loading_report_artifact(
    report_path: str | Path,
    payload: dict[str, Any],
) -> None:
    """Atomically write a metadata loading report using the canonical renderer."""

    _write_report_artifact(Path(report_path), payload)


def _dataset_size_from_metadata(
    metadata: dict[str, str | int | float] | None,
) -> dict[str, int] | None:
    if metadata is None:
        return None
    return {
        "total_frames": int(metadata["total_frames"]),
        "frame_width": int(metadata["frame_width"]),
        "frame_height": int(metadata["frame_height"]),
    }


def _validate_positive_int(field_name: str, value: Any) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _validate_positive_number(field_name: str, value: Any) -> float:
    if not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    numeric = float(value)
    if numeric <= 0:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _validate_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _write_report_artifact(report_path: Path, payload: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = report_path.with_name(f".{report_path.name}.tmp")
    tmp_path.write_text(
        render_metadata_loading_report(payload),
        encoding="utf-8",
    )
    os.replace(tmp_path, report_path)
