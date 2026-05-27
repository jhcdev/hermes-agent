from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator


ANNOTATION_ARTIFACT = "annotations.jsonl"
FRAME_REVIEW_ARTIFACT = "frame_reviews.jsonl"
NAVIGATION_REVIEW_ARTIFACT = "navigation_review_export.json"
TAXONOMY_ARTIFACT = "taxonomy.json"
ANNOTATION_OUTPUT_SCHEMA_VERSION = "tsr-annotation-output-v1"
FRAME_REVIEW_OUTPUT_SCHEMA_VERSION = "tsr-frame-review-output-v1"
NAVIGATION_REVIEW_SCHEMA_VERSION = "tsr-navigation-review-v1"


@dataclass(frozen=True)
class BoxAnnotation:
    """Serializable box annotation record with a deterministic identifier."""

    annotation_id: str
    video_id: str
    frame_index: int
    label: str
    bbox: tuple[float, float, float, float]
    kind: str = "box"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["bbox"] = list(self.bbox)
        return record


@dataclass(frozen=True)
class PolygonAnnotation:
    """Serializable polygon annotation record with a deterministic identifier."""

    annotation_id: str
    video_id: str
    frame_index: int
    label: str
    points: tuple[tuple[float, float], ...]
    kind: str = "polygon"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["points"] = [[x, y] for x, y in self.points]
        return record


@dataclass(frozen=True)
class FrameReviewStatus:
    """Serializable frame-level review status record."""

    review_id: str
    video_id: str
    frame_index: int
    reviewed: bool
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_record(self) -> dict[str, Any]:
        return asdict(self)


def create_box_annotation(
    project_dir: str | Path,
    *,
    video_id: str,
    frame_index: int,
    label: str,
    bbox: tuple[float, float, float, float] | list[float],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or replace a box annotation and return its stable artifact.

    The annotation ID is derived from the immutable annotation identity fields:
    video, frame, label, and normalized box coordinates. The JSONL store is
    rewritten as a stream so large projects do not need to load the full
    annotation set into memory.
    """

    project_path = Path(project_dir)
    project_path.mkdir(parents=True, exist_ok=True)

    normalized_bbox = _normalize_bbox(bbox)
    annotation = BoxAnnotation(
        annotation_id=_stable_box_id(video_id, frame_index, label, normalized_bbox),
        video_id=_validate_text("video_id", video_id),
        frame_index=_validate_frame_index(frame_index),
        label=_validate_text("label", label),
        bbox=normalized_bbox,
        metadata=dict(metadata or {}),
    )

    artifact_path = project_path / ANNOTATION_ARTIFACT
    _upsert_jsonl_record(artifact_path, annotation.to_json_record())

    return {
        "annotation_id": annotation.annotation_id,
        "artifact_path": str(artifact_path),
        "annotation": annotation.to_json_record(),
        "schema_version": ANNOTATION_OUTPUT_SCHEMA_VERSION,
    }


def create_polygon_annotation(
    project_dir: str | Path,
    *,
    video_id: str,
    frame_index: int,
    label: str,
    points: list[list[float]] | list[tuple[float, float]] | tuple[tuple[float, float], ...],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or replace a polygon annotation and return its stable artifact."""

    project_path = Path(project_dir)
    project_path.mkdir(parents=True, exist_ok=True)

    normalized_points = _normalize_polygon_points(points)
    annotation = PolygonAnnotation(
        annotation_id=_stable_polygon_id(video_id, frame_index, label, normalized_points),
        video_id=_validate_text("video_id", video_id),
        frame_index=_validate_frame_index(frame_index),
        label=_validate_text("label", label),
        points=normalized_points,
        metadata=dict(metadata or {}),
    )

    artifact_path = project_path / ANNOTATION_ARTIFACT
    _upsert_jsonl_record(artifact_path, annotation.to_json_record())

    return {
        "annotation_id": annotation.annotation_id,
        "artifact_path": str(artifact_path),
        "annotation": annotation.to_json_record(),
        "schema_version": ANNOTATION_OUTPUT_SCHEMA_VERSION,
    }


def assign_annotation_class(
    project_dir: str | Path,
    *,
    annotation_id: str,
    class_id: int,
    class_name: str,
    taxonomy_path: str | Path | None = None,
) -> dict[str, Any]:
    """Assign a selected class to an existing annotation."""

    project_path = Path(project_dir)
    artifact_path = project_path / ANNOTATION_ARTIFACT
    target_id = _validate_text("annotation_id", annotation_id)
    selected_class_id = _validate_class_id(class_id)
    selected_class_name = _validate_text("class_name", class_name)
    _validate_known_taxonomy_class(
        project_path,
        class_id=selected_class_id,
        class_name=selected_class_name,
        taxonomy_path=taxonomy_path,
    )

    updated_annotation = _update_annotation_record(
        artifact_path,
        target_id,
        class_id=selected_class_id,
        class_name=selected_class_name,
    )

    return {
        "ok": True,
        "annotation_id": target_id,
        "artifact_path": str(artifact_path),
        "annotation": updated_annotation,
        "schema_version": ANNOTATION_OUTPUT_SCHEMA_VERSION,
    }


def set_frame_review_status(
    project_dir: str | Path,
    *,
    video_id: str,
    frame_index: int,
    reviewed: bool,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record and return stable reviewed/unreviewed status for one frame."""

    project_path = Path(project_dir)
    project_path.mkdir(parents=True, exist_ok=True)

    status_record = FrameReviewStatus(
        review_id=_stable_frame_review_id(video_id, frame_index),
        video_id=_validate_text("video_id", video_id),
        frame_index=_validate_frame_index(frame_index),
        reviewed=_validate_reviewed(reviewed),
        status="reviewed" if reviewed else "unreviewed",
        metadata=dict(metadata or {}),
    )

    artifact_path = project_path / FRAME_REVIEW_ARTIFACT
    _upsert_jsonl_record(artifact_path, status_record.to_json_record(), id_field="review_id")

    return {
        "review_id": status_record.review_id,
        "artifact_path": str(artifact_path),
        "review": status_record.to_json_record(),
        "schema_version": FRAME_REVIEW_OUTPUT_SCHEMA_VERSION,
    }


def handle_frame_review_command(
    project_dir: str | Path,
    command: str,
    *,
    video_id: str,
    frame_index: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a frame review command and return stable observable status."""

    normalized = command.strip().lower().replace("-", "_")
    if normalized in {"review", "reviewed", "mark_reviewed"}:
        return set_frame_review_status(
            project_dir,
            video_id=video_id,
            frame_index=frame_index,
            reviewed=True,
            metadata=metadata,
        )
    if normalized in {"unreview", "unreviewed", "mark_unreviewed"}:
        return set_frame_review_status(
            project_dir,
            video_id=video_id,
            frame_index=frame_index,
            reviewed=False,
            metadata=metadata,
        )
    raise ValueError(f"unsupported frame review command: {command}")


def iter_box_annotations(project_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Yield persisted box annotations without loading the full project."""

    artifact_path = Path(project_dir) / ANNOTATION_ARTIFACT
    if not artifact_path.exists():
        return

    with artifact_path.open("r", encoding="utf-8") as annotation_file:
        for line in annotation_file:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("kind") == "box":
                yield _normalize_box_record(record)


def iter_polygon_annotations(project_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Yield persisted polygon annotations without loading the full project."""

    artifact_path = Path(project_dir) / ANNOTATION_ARTIFACT
    if not artifact_path.exists():
        return

    with artifact_path.open("r", encoding="utf-8") as annotation_file:
        for line in annotation_file:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("kind") == "polygon":
                yield _normalize_polygon_record(record)


def iter_frame_review_statuses(project_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Yield persisted frame review statuses without loading the full project."""

    artifact_path = Path(project_dir) / FRAME_REVIEW_ARTIFACT
    if not artifact_path.exists():
        return

    with artifact_path.open("r", encoding="utf-8") as review_file:
        for line in review_file:
            if not line.strip():
                continue
            yield _normalize_frame_review_record(json.loads(line))


def load_box_annotation(project_dir: str | Path, annotation_id: str) -> dict[str, Any] | None:
    """Load one persisted box annotation by ID."""

    target_id = _validate_text("annotation_id", annotation_id)
    for record in iter_box_annotations(project_dir):
        if record["annotation_id"] == target_id:
            return record
    return None


def load_polygon_annotation(project_dir: str | Path, annotation_id: str) -> dict[str, Any] | None:
    """Load one persisted polygon annotation by ID."""

    target_id = _validate_text("annotation_id", annotation_id)
    for record in iter_polygon_annotations(project_dir):
        if record["annotation_id"] == target_id:
            return record
    return None


def load_frame_review_status(
    project_dir: str | Path,
    *,
    video_id: str,
    frame_index: int,
) -> dict[str, Any] | None:
    """Load one persisted frame review status by stable frame identity."""

    target_id = _stable_frame_review_id(video_id, frame_index)
    for record in iter_frame_review_statuses(project_dir):
        if record["review_id"] == target_id:
            return record
    return None


def export_navigation_review_artifact(
    project_dir: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Export deterministic navigation and review state for a project.

    The export is intentionally derived from the append-friendly JSONL stores
    instead of becoming a second source of truth. Records are normalized,
    grouped by frame identity, sorted by stable keys, and serialized with fixed
    JSON settings so identical inputs produce byte-for-byte identical output.
    """

    project_path = Path(project_dir)
    target_path = Path(output_path) if output_path is not None else project_path / NAVIGATION_REVIEW_ARTIFACT
    target_path.parent.mkdir(parents=True, exist_ok=True)

    frames: dict[tuple[str, int], dict[str, Any]] = {}
    annotations = sorted(
        [*iter_box_annotations(project_path), *iter_polygon_annotations(project_path)],
        key=_annotation_sort_key,
    )
    reviews = sorted(iter_frame_review_statuses(project_path), key=_frame_review_sort_key)

    for annotation in annotations:
        frame = _frame_export_record(frames, annotation["video_id"], annotation["frame_index"])
        frame["annotations"].append(annotation)

    for review in reviews:
        frame = _frame_export_record(frames, review["video_id"], review["frame_index"])
        frame["review"] = review
        frame["review_status"] = _review_status_export_record(review)

    ordered_frames = [frames[key] for key in sorted(frames)]
    visited_frame_ids = [_frame_identifier(video_id, frame_index) for video_id, frame_index in sorted(frames)]
    export = {
        "format": NAVIGATION_REVIEW_SCHEMA_VERSION,
        "summary": {
            "annotation_count": len(annotations),
            "frame_count": len(ordered_frames),
            "review_count": len(reviews),
            "video_count": len({video_id for video_id, _frame_index in frames}),
        },
        "schema_version": NAVIGATION_REVIEW_SCHEMA_VERSION,
        "visited_frame_ids": visited_frame_ids,
        "frames": ordered_frames,
    }

    _write_stable_json(target_path, export)
    return {
        "artifact_path": str(target_path),
        "export": export,
        "schema_version": NAVIGATION_REVIEW_SCHEMA_VERSION,
    }


def _stable_box_id(
    video_id: str,
    frame_index: int,
    label: str,
    bbox: tuple[float, float, float, float],
) -> str:
    payload = {
        "bbox": list(bbox),
        "frame_index": _validate_frame_index(frame_index),
        "kind": "box",
        "label": _validate_text("label", label),
        "video_id": _validate_text("video_id", video_id),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"box_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def _stable_polygon_id(
    video_id: str,
    frame_index: int,
    label: str,
    points: tuple[tuple[float, float], ...],
) -> str:
    payload = {
        "frame_index": _validate_frame_index(frame_index),
        "kind": "polygon",
        "label": _validate_text("label", label),
        "points": [[x, y] for x, y in points],
        "video_id": _validate_text("video_id", video_id),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"polygon_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def _stable_frame_review_id(video_id: str, frame_index: int) -> str:
    payload = {
        "frame_index": _validate_frame_index(frame_index),
        "video_id": _validate_text("video_id", video_id),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"frame_review_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def _annotation_sort_key(record: dict[str, Any]) -> tuple[str, int, str, str, str]:
    return (
        record["video_id"],
        record["frame_index"],
        record["label"],
        record["kind"],
        record["annotation_id"],
    )


def _frame_review_sort_key(record: dict[str, Any]) -> tuple[str, int, str]:
    return (
        record["video_id"],
        record["frame_index"],
        record["review_id"],
    )


def _frame_export_record(
    frames: dict[tuple[str, int], dict[str, Any]],
    video_id: str,
    frame_index: int,
) -> dict[str, Any]:
    key = (video_id, frame_index)
    if key not in frames:
        frames[key] = {
            "annotations": [],
            "frame_index": frame_index,
            "review": None,
            "review_status": _review_status_export_record(None),
            "video_id": video_id,
        }
    return frames[key]


def _frame_identifier(video_id: str, frame_index: int) -> str:
    return f"{video_id}:{frame_index}"


def _review_status_export_record(review: dict[str, Any] | None) -> dict[str, Any]:
    if review is None:
        return {
            "reviewed": False,
            "source": "default",
            "status": "unreviewed",
        }

    return {
        "reviewed": review["reviewed"],
        "review_id": review["review_id"],
        "source": "frame_reviews",
        "status": review["status"],
    }


def _write_stable_json(path: Path, payload: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            json.dump(payload, temp_file, sort_keys=True, separators=(",", ":"))
            temp_file.write("\n")
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _normalize_bbox(bbox: tuple[float, float, float, float] | list[float]) -> tuple[float, float, float, float]:
    if len(bbox) != 4:
        raise ValueError("bbox must contain exactly four values: x, y, width, height")

    x, y, width, height = (float(value) for value in bbox)
    if width <= 0 or height <= 0:
        raise ValueError("bbox width and height must be positive")
    if x < 0 or y < 0:
        raise ValueError("bbox x and y must be non-negative")

    return tuple(round(value, 6) for value in (x, y, width, height))


def _normalize_polygon_points(
    points: list[list[float]] | list[tuple[float, float]] | tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    if len(points) < 3:
        raise ValueError("polygon points must contain at least three vertices")

    normalized: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        if len(point) != 2:
            raise ValueError(f"polygon point {index} must contain exactly two values: x, y")
        x, y = (float(value) for value in point)
        if x < 0 or y < 0:
            raise ValueError("polygon point coordinates must be non-negative")
        normalized.append((round(x, 6), round(y, 6)))

    if len(set(normalized)) < 3:
        raise ValueError("polygon points must include at least three distinct vertices")

    return tuple(normalized)


def _validate_frame_index(frame_index: int) -> int:
    if not isinstance(frame_index, int):
        raise TypeError("frame_index must be an integer")
    if frame_index < 0:
        raise ValueError("frame_index must be non-negative")
    return frame_index


def _validate_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_reviewed(reviewed: bool) -> bool:
    if not isinstance(reviewed, bool):
        raise TypeError("reviewed must be a boolean")
    return reviewed


def _validate_class_id(class_id: int) -> int:
    if isinstance(class_id, bool) or not isinstance(class_id, int):
        raise ValueError("class_id must be an integer")
    if class_id < 0:
        raise ValueError("class_id must be non-negative")
    return class_id


def _validate_known_taxonomy_class(
    project_path: Path,
    *,
    class_id: int,
    class_name: str,
    taxonomy_path: str | Path | None,
) -> None:
    resolved_taxonomy_path = Path(taxonomy_path) if taxonomy_path is not None else project_path / TAXONOMY_ARTIFACT
    if not resolved_taxonomy_path.exists():
        return

    classes = _load_taxonomy_classes(resolved_taxonomy_path)
    if (class_id, class_name) not in classes:
        raise ValueError(f"unknown-class: class_id={class_id} class_name={class_name!r}")


def _load_taxonomy_classes(path: Path) -> set[tuple[int, str]]:
    with path.open("r", encoding="utf-8") as taxonomy_file:
        payload = json.load(taxonomy_file)

    raw_classes = payload.get("classes") if isinstance(payload, dict) else payload
    if raw_classes is None and isinstance(payload, dict) and isinstance(payload.get("taxonomy"), dict):
        raw_classes = payload["taxonomy"].get("classes")
    if not isinstance(raw_classes, list):
        raise ValueError("taxonomy classes must be a list")

    classes: set[tuple[int, str]] = set()
    for index, raw_class in enumerate(raw_classes):
        if not isinstance(raw_class, dict):
            raise ValueError(f"taxonomy class {index} must be an object")
        taxonomy_class_id = _validate_class_id(raw_class.get("id", raw_class.get("class_id")))
        taxonomy_class_name = _validate_text(
            "taxonomy class name",
            raw_class.get("name", raw_class.get("class_name")),
        )
        classes.add((taxonomy_class_id, taxonomy_class_name))

    return classes


def _normalize_box_record(record: dict[str, Any]) -> dict[str, Any]:
    return BoxAnnotation(
        annotation_id=_validate_text("annotation_id", record.get("annotation_id", "")),
        video_id=_validate_text("video_id", record.get("video_id", "")),
        frame_index=_validate_frame_index(record.get("frame_index")),
        label=_validate_text("label", record.get("label", "")),
        bbox=_normalize_bbox(record.get("bbox", [])),
        kind="box",
        metadata=dict(record.get("metadata") or {}),
    ).to_json_record()


def _normalize_annotation_record(record: dict[str, Any]) -> dict[str, Any]:
    kind = record.get("kind")
    if kind == "box":
        return _normalize_box_record(record)
    if kind == "polygon":
        return _normalize_polygon_record(record)
    raise ValueError(f"unsupported annotation kind: {kind}")


def _with_assigned_class(record: dict[str, Any], *, class_id: int, class_name: str) -> dict[str, Any]:
    updated = dict(record)
    updated["label"] = class_name
    updated["metadata"] = {
        **dict(record.get("metadata") or {}),
        "class_id": class_id,
        "class_name": class_name,
    }
    return _normalize_annotation_record(updated)


def _normalize_polygon_record(record: dict[str, Any]) -> dict[str, Any]:
    return PolygonAnnotation(
        annotation_id=_validate_text("annotation_id", record.get("annotation_id", "")),
        video_id=_validate_text("video_id", record.get("video_id", "")),
        frame_index=_validate_frame_index(record.get("frame_index")),
        label=_validate_text("label", record.get("label", "")),
        points=_normalize_polygon_points(record.get("points", [])),
        kind="polygon",
        metadata=dict(record.get("metadata") or {}),
    ).to_json_record()


def _update_annotation_record(
    path: Path,
    annotation_id: str,
    *,
    class_id: int,
    class_name: str,
) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"annotation artifact does not exist: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    updated_record: dict[str, Any] | None = None

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            with path.open("r", encoding="utf-8") as current_file:
                for line in current_file:
                    if not line.strip():
                        continue
                    current = json.loads(line)
                    if current.get("annotation_id") == annotation_id:
                        updated_record = _with_assigned_class(
                            current,
                            class_id=class_id,
                            class_name=class_name,
                        )
                        temp_file.write(json.dumps(updated_record, sort_keys=True) + "\n")
                    else:
                        temp_file.write(json.dumps(current, sort_keys=True) + "\n")

        if updated_record is None:
            raise KeyError(f"annotation not found: {annotation_id}")

        os.replace(temp_name, path)
        return updated_record
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _normalize_frame_review_record(record: dict[str, Any]) -> dict[str, Any]:
    reviewed = _validate_reviewed(record.get("reviewed"))
    status = _validate_text("status", record.get("status", ""))
    expected_status = "reviewed" if reviewed else "unreviewed"
    if status != expected_status:
        raise ValueError("frame review status must match reviewed boolean")

    return FrameReviewStatus(
        review_id=_validate_text("review_id", record.get("review_id", "")),
        video_id=_validate_text("video_id", record.get("video_id", "")),
        frame_index=_validate_frame_index(record.get("frame_index")),
        reviewed=reviewed,
        status=status,
        metadata=dict(record.get("metadata") or {}),
    ).to_json_record()


def _upsert_jsonl_record(path: Path, record: dict[str, Any], *, id_field: str = "annotation_id") -> None:
    record_id = record[id_field]
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    replaced = False

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            if path.exists():
                with path.open("r", encoding="utf-8") as current_file:
                    for line in current_file:
                        if not line.strip():
                            continue
                        current = json.loads(line)
                        if current.get(id_field) == record_id:
                            temp_file.write(json.dumps(record, sort_keys=True) + "\n")
                            replaced = True
                        else:
                            temp_file.write(json.dumps(current, sort_keys=True) + "\n")

            if not replaced:
                temp_file.write(json.dumps(record, sort_keys=True) + "\n")

        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
