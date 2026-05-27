from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tsr_video_annotation_tool import (
    assign_annotation_class,
    create_box_annotation,
    create_polygon_annotation,
    export_navigation_review_artifact,
    handle_frame_review_command,
    iter_polygon_annotations,
    load_box_annotation,
    load_frame_review_status,
    load_polygon_annotation,
    run_public_contract_check,
    set_frame_review_status,
)
from tsr_video_annotation_tool.public_contract import DEFAULT_PUBLIC_MODULES, DEFAULT_PUBLIC_SYMBOLS


REPO_ROOT = Path(__file__).resolve().parents[1]


def _assert_single_line_json(stdout: str) -> dict[str, object]:
    assert stdout.endswith("\n")
    assert stdout.count("\n") == 1
    return json.loads(stdout)


def test_tsr_annotate_script_entry_point_reports_readiness_without_asset_errors():
    project_metadata = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    entry_point = project_metadata["project"]["scripts"]["tsr-annotate"]
    module_name, function_name = entry_point.split(":", 1)

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                f"from {module_name} import {function_name}\n"
                f"raise SystemExit({function_name}(['--help']))\n"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    combined_output = completed.stdout + completed.stderr
    assert completed.returncode == 0
    assert "usage: tsr-annotate" in completed.stdout
    assert "ImportError" not in combined_output
    assert "ModuleNotFoundError" not in combined_output
    assert "FileNotFoundError" not in combined_output
    assert "No such file or directory" not in combined_output


def test_public_contract_check_api_returns_machine_readable_status():
    result = run_public_contract_check(
        modules=["tsr_video_annotation_tool"],
        symbols=["tsr_video_annotation_tool:create_box_annotation"],
    )

    assert result == {
        "ok": True,
        "schema_version": "tsr-public-contract-check-v1",
        "summary": {
            "modules_checked": 1,
            "modules_failed": 0,
            "symbols_checked": 1,
            "symbols_failed": 0,
        },
        "modules": [{"module": "tsr_video_annotation_tool", "ok": True, "error": None}],
        "symbols": [
            {
                "module": "tsr_video_annotation_tool",
                "symbol": "create_box_annotation",
                "ok": True,
                "error": None,
            }
        ],
    }


def test_public_contract_check_cli_emits_json_and_nonzero_on_missing_symbol():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "check-symbols",
            "--module",
            "tsr_video_annotation_tool",
            "--symbol",
            "tsr_video_annotation_tool:missing_symbol",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = _assert_single_line_json(completed.stdout)
    assert completed.returncode == 1
    assert payload["ok"] is False
    assert payload["schema_version"] == "tsr-public-contract-check-v1"
    assert payload["summary"] == {
        "modules_checked": 1,
        "modules_failed": 0,
        "symbols_checked": 1,
        "symbols_failed": 1,
    }
    assert payload["symbols"][0]["module"] == "tsr_video_annotation_tool"
    assert payload["symbols"][0]["symbol"] == "missing_symbol"
    assert payload["symbols"][0]["ok"] is False
    assert "AttributeError" in payload["symbols"][0]["error"]


def test_public_contract_check_cli_lists_every_default_module_and_symbol():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "check-symbols",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    payload = _assert_single_line_json(completed.stdout)
    expected_symbols = [
        {"module": module_name, "symbol": symbol_name}
        for module_name, symbol_name in (symbol_spec.split(":", 1) for symbol_spec in DEFAULT_PUBLIC_SYMBOLS)
    ]

    assert completed.returncode == 0
    assert payload["ok"] is True
    assert payload["summary"]["modules_checked"] == len(DEFAULT_PUBLIC_MODULES)
    assert payload["summary"]["symbols_checked"] == len(DEFAULT_PUBLIC_SYMBOLS)
    assert [module_check["module"] for module_check in payload["modules"]] == list(DEFAULT_PUBLIC_MODULES)
    assert [
        {"module": symbol_check["module"], "symbol": symbol_check["symbol"]}
        for symbol_check in payload["symbols"]
    ] == expected_symbols


def test_create_box_annotation_returns_stable_id_and_artifact(tmp_path):
    first = create_box_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=42,
        label="vehicle",
        bbox=(10, 20, 30, 40),
        metadata={"source": "gt"},
    )
    second = create_box_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=42,
        label="vehicle",
        bbox=(10.0, 20.0, 30.0, 40.0),
        metadata={"source": "gt-revised"},
    )

    assert first["annotation_id"] == second["annotation_id"]
    assert first["annotation_id"].startswith("box_")
    assert first["schema_version"] == "tsr-annotation-output-v1"
    assert set(first) == {"annotation_id", "artifact_path", "annotation", "schema_version"}

    artifact_path = tmp_path / "annotations.jsonl"
    assert second["artifact_path"] == str(artifact_path)

    records = [json.loads(line) for line in artifact_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["annotation_id"] == first["annotation_id"]
    assert records[0]["bbox"] == [10.0, 20.0, 30.0, 40.0]
    assert records[0]["metadata"] == {"source": "gt-revised"}


def test_create_box_annotation_cli_emits_observable_artifact(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "create-box",
            "--project-dir",
            str(tmp_path),
            "--video-id",
            "camera-a",
            "--frame-index",
            "7",
            "--label",
            "pedestrian",
            "--bbox",
            "1",
            "2",
            "3",
            "4",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = _assert_single_line_json(completed.stdout)
    assert payload["annotation_id"].startswith("box_")
    assert payload["schema_version"] == "tsr-annotation-output-v1"
    assert payload["artifact_path"] == str(tmp_path / "annotations.jsonl")
    assert payload["annotation"]["frame_index"] == 7
    assert (tmp_path / "annotations.jsonl").exists()


def test_created_box_annotation_reloads_unchanged(tmp_path):
    created = create_box_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=1000,
        label="traffic-sign",
        bbox=(12.25, 34.5, 56.75, 78.125),
        metadata={"workflow": "gt", "reviewed": False},
    )

    reloaded = load_box_annotation(tmp_path, created["annotation_id"])

    assert reloaded == created["annotation"]


def test_assign_annotation_class_updates_existing_annotation_with_success_response(tmp_path):
    created = create_box_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=1000,
        label="unclassified",
        bbox=(12.25, 34.5, 56.75, 78.125),
        metadata={"workflow": "gt", "reviewed": False},
    )

    assigned = assign_annotation_class(
        tmp_path,
        annotation_id=created["annotation_id"],
        class_id=17,
        class_name="traffic-sign",
    )

    expected_annotation = {
        **created["annotation"],
        "label": "traffic-sign",
        "metadata": {
            "workflow": "gt",
            "reviewed": False,
            "class_id": 17,
            "class_name": "traffic-sign",
        },
    }
    assert assigned == {
        "ok": True,
        "annotation_id": created["annotation_id"],
        "artifact_path": str(tmp_path / "annotations.jsonl"),
        "annotation": expected_annotation,
        "schema_version": "tsr-annotation-output-v1",
    }
    assert load_box_annotation(tmp_path, created["annotation_id"]) == expected_annotation


@pytest.mark.parametrize(
    ("class_id", "class_name", "expected_message"),
    [
        (True, "traffic-sign", "class_id must be an integer"),
        ("17", "traffic-sign", "class_id must be an integer"),
        (1.5, "traffic-sign", "class_id must be an integer"),
        (-1, "traffic-sign", "class_id must be non-negative"),
        (17, "", "class_name must be a non-empty string"),
        (17, "   ", "class_name must be a non-empty string"),
        (17, None, "class_name must be a non-empty string"),
    ],
)
def test_assign_annotation_class_rejects_malformed_class_values_with_deterministic_error(
    tmp_path, class_id, class_name, expected_message
):
    created = create_box_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=1000,
        label="unclassified",
        bbox=(12.25, 34.5, 56.75, 78.125),
        metadata={"workflow": "gt", "reviewed": False},
    )
    artifact_path = tmp_path / "annotations.jsonl"
    artifact_before = artifact_path.read_bytes()

    with pytest.raises(ValueError, match=f"^{re.escape(expected_message)}$"):
        assign_annotation_class(
            tmp_path,
            annotation_id=created["annotation_id"],
            class_id=class_id,
            class_name=class_name,
        )

    assert artifact_path.read_bytes() == artifact_before
    assert load_box_annotation(tmp_path, created["annotation_id"]) == created["annotation"]


def test_assign_annotation_class_rejects_unknown_class_from_project_taxonomy(tmp_path):
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(
            {
                "classes": [
                    {"id": 17, "name": "traffic-sign"},
                    {"id": 23, "name": "traffic-light"},
                ]
            }
        ),
        encoding="utf-8",
    )
    created = create_box_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=1000,
        label="unclassified",
        bbox=(12.25, 34.5, 56.75, 78.125),
        metadata={"workflow": "gt", "reviewed": False},
    )
    artifact_path = tmp_path / "annotations.jsonl"
    artifact_before = artifact_path.read_bytes()

    with pytest.raises(ValueError, match="^unknown-class: class_id=99 class_name='speed-limit'$"):
        assign_annotation_class(
            tmp_path,
            annotation_id=created["annotation_id"],
            class_id=99,
            class_name="speed-limit",
        )

    assert artifact_path.read_bytes() == artifact_before
    assert load_box_annotation(tmp_path, created["annotation_id"]) == created["annotation"]


def test_assign_annotation_class_cli_rejects_unknown_class_with_deterministic_error(tmp_path):
    taxonomy_path = tmp_path / "project-taxonomy.json"
    taxonomy_path.write_text(
        json.dumps({"classes": [{"id": 17, "name": "traffic-sign"}]}),
        encoding="utf-8",
    )
    created = create_box_annotation(
        tmp_path,
        video_id="camera-c",
        frame_index=1001,
        label="unclassified",
        bbox=(20, 30, 40, 50),
        metadata={"workflow": "gt"},
    )
    artifact_path = tmp_path / "annotations.jsonl"
    artifact_before = artifact_path.read_bytes()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "assign-class",
            "--project-dir",
            str(tmp_path),
            "--annotation-id",
            created["annotation_id"],
            "--class-id",
            "99",
            "--class-name",
            "speed-limit",
            "--taxonomy-path",
            str(taxonomy_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.strip() == "unknown-class: class_id=99 class_name='speed-limit'"
    assert artifact_path.read_bytes() == artifact_before
    assert load_box_annotation(tmp_path, created["annotation_id"]) == created["annotation"]


def test_assign_annotation_class_cli_persists_reloadable_class_artifact(tmp_path):
    created = create_box_annotation(
        tmp_path,
        video_id="camera-c",
        frame_index=1001,
        label="unclassified",
        bbox=(20, 30, 40, 50),
        metadata={"workflow": "gt"},
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "assign-class",
            "--project-dir",
            str(tmp_path),
            "--annotation-id",
            created["annotation_id"],
            "--class-id",
            "23",
            "--class-name",
            "traffic-light",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = _assert_single_line_json(completed.stdout)
    expected_annotation = {
        **created["annotation"],
        "label": "traffic-light",
        "metadata": {
            "workflow": "gt",
            "class_id": 23,
            "class_name": "traffic-light",
        },
    }

    assert payload == {
        "ok": True,
        "annotation_id": created["annotation_id"],
        "artifact_path": str(tmp_path / "annotations.jsonl"),
        "annotation": expected_annotation,
        "schema_version": "tsr-annotation-output-v1",
    }
    assert load_box_annotation(tmp_path, created["annotation_id"]) == expected_annotation
    artifact_records = [
        json.loads(line) for line in (tmp_path / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert artifact_records == [expected_annotation]


def test_create_polygon_annotation_returns_stable_id_and_artifact(tmp_path):
    first = create_polygon_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=43,
        label="lane-boundary",
        points=[(10, 20), (30, 20), (35, 45), (12, 50)],
        metadata={"source": "gt"},
    )
    second = create_polygon_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=43,
        label="lane-boundary",
        points=[[10.0, 20.0], [30.0, 20.0], [35.0, 45.0], [12.0, 50.0]],
        metadata={"source": "gt-revised"},
    )

    assert first["annotation_id"] == second["annotation_id"]
    assert first["annotation_id"].startswith("polygon_")
    assert first["schema_version"] == "tsr-annotation-output-v1"

    artifact_path = tmp_path / "annotations.jsonl"
    assert second["artifact_path"] == str(artifact_path)

    records = [json.loads(line) for line in artifact_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0] == {
        "annotation_id": first["annotation_id"],
        "frame_index": 43,
        "kind": "polygon",
        "label": "lane-boundary",
        "metadata": {"source": "gt-revised"},
        "points": [[10.0, 20.0], [30.0, 20.0], [35.0, 45.0], [12.0, 50.0]],
        "video_id": "camera-a",
    }


def test_create_polygon_annotation_cli_emits_observable_artifact(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "create-polygon",
            "--project-dir",
            str(tmp_path),
            "--video-id",
            "camera-a",
            "--frame-index",
            "8",
            "--label",
            "road-surface",
            "--points",
            "[[1, 2], [3, 2], [3, 4], [1, 4]]",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = _assert_single_line_json(completed.stdout)
    assert payload["annotation_id"].startswith("polygon_")
    assert payload["schema_version"] == "tsr-annotation-output-v1"
    assert payload["artifact_path"] == str(tmp_path / "annotations.jsonl")
    assert payload["annotation"] == {
        "annotation_id": payload["annotation_id"],
        "frame_index": 8,
        "kind": "polygon",
        "label": "road-surface",
        "metadata": {},
        "points": [[1.0, 2.0], [3.0, 2.0], [3.0, 4.0], [1.0, 4.0]],
        "video_id": "camera-a",
    }
    assert (tmp_path / "annotations.jsonl").exists()


def test_created_polygon_annotation_reloads_unchanged(tmp_path):
    created = create_polygon_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=1001,
        label="work-zone",
        points=[(12.25, 34.5), (56.75, 34.5), (56.75, 78.125), (12.25, 78.125)],
        metadata={"workflow": "gt", "reviewed": False},
    )

    reloaded = load_polygon_annotation(tmp_path, created["annotation_id"])

    assert reloaded == created["annotation"]


def test_polygon_annotation_persists_geometry_and_metadata_after_project_reopen(tmp_path):
    create_box_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=1001,
        label="traffic-cone",
        bbox=(1, 2, 3, 4),
        metadata={"workflow": "gt"},
    )
    created = create_polygon_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=1001,
        label="work-zone",
        points=[(12.25, 34.5), (56.75, 34.5), (56.75, 78.125), (12.25, 78.125)],
        metadata={
            "workflow": "gt",
            "class_id": 17,
            "reviewed": False,
            "source": "polygon-tool",
        },
    )

    reopened_project_dir = Path(str(tmp_path))
    reloaded = load_polygon_annotation(reopened_project_dir, created["annotation_id"])
    streamed_polygons = list(iter_polygon_annotations(reopened_project_dir))

    assert reloaded is not None
    assert reloaded["annotation_id"] == created["annotation_id"]
    assert reloaded["points"] == [
        [12.25, 34.5],
        [56.75, 34.5],
        [56.75, 78.125],
        [12.25, 78.125],
    ]
    assert reloaded["metadata"] == {
        "workflow": "gt",
        "class_id": 17,
        "reviewed": False,
        "source": "polygon-tool",
    }
    assert streamed_polygons == [reloaded]


def test_frame_review_api_records_and_reloads_stable_status(tmp_path):
    reviewed = set_frame_review_status(
        tmp_path,
        video_id="camera-a",
        frame_index=1000,
        reviewed=True,
        metadata={"reviewer": "qa-1"},
    )

    assert reviewed["review_id"].startswith("frame_review_")
    assert reviewed["schema_version"] == "tsr-frame-review-output-v1"
    assert reviewed["artifact_path"] == str(tmp_path / "frame_reviews.jsonl")
    assert reviewed["review"] == {
        "review_id": reviewed["review_id"],
        "video_id": "camera-a",
        "frame_index": 1000,
        "reviewed": True,
        "status": "reviewed",
        "metadata": {"reviewer": "qa-1"},
    }
    assert load_frame_review_status(tmp_path, video_id="camera-a", frame_index=1000) == reviewed["review"]


def test_frame_review_command_persists_reviewed_and_unreviewed_observable_output(tmp_path):
    reviewed = handle_frame_review_command(
        tmp_path,
        "mark-reviewed",
        video_id="camera-a",
        frame_index=7,
        metadata={"source": "gt-loop"},
    )
    unreviewed = handle_frame_review_command(
        tmp_path,
        "mark-unreviewed",
        video_id="camera-a",
        frame_index=7,
        metadata={"source": "delta-loop"},
    )

    assert reviewed["review_id"] == unreviewed["review_id"]
    assert reviewed["review"]["status"] == "reviewed"
    assert unreviewed["review"]["status"] == "unreviewed"

    records = [json.loads(line) for line in (tmp_path / "frame_reviews.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records == [unreviewed["review"]]
    assert load_frame_review_status(tmp_path, video_id="camera-a", frame_index=7) == unreviewed["review"]


def test_review_frame_cli_emits_persisted_review_status(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "review-frame",
            "--project-dir",
            str(tmp_path),
            "--video-id",
            "camera-a",
            "--frame-index",
            "8",
            "--status",
            "reviewed",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = _assert_single_line_json(completed.stdout)
    assert payload["review_id"].startswith("frame_review_")
    assert payload["schema_version"] == "tsr-frame-review-output-v1"
    assert payload["artifact_path"] == str(tmp_path / "frame_reviews.jsonl")
    assert payload["review"]["frame_index"] == 8
    assert payload["review"]["reviewed"] is True
    assert payload["review"]["status"] == "reviewed"
    assert load_frame_review_status(tmp_path, video_id="camera-a", frame_index=8) == payload["review"]


def test_navigation_review_export_is_deterministic_and_repeatable(tmp_path):
    later_box = create_box_annotation(
        tmp_path,
        video_id="camera-b",
        frame_index=2,
        label="vehicle",
        bbox=(20, 30, 40, 50),
        metadata={"z": "last", "a": "first"},
    )
    earlier_polygon = create_polygon_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=1,
        label="lane",
        points=[(3, 4), (8, 4), (8, 9), (3, 9)],
        metadata={"source": "gt"},
    )
    earlier_box = create_box_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=1,
        label="sign",
        bbox=(1, 2, 3, 4),
        metadata={"source": "delta"},
    )
    reviewed = set_frame_review_status(
        tmp_path,
        video_id="camera-a",
        frame_index=1,
        reviewed=True,
        metadata={"reviewer": "qa"},
    )

    first = export_navigation_review_artifact(tmp_path, tmp_path / "first.json")
    second = export_navigation_review_artifact(tmp_path, tmp_path / "second.json")

    assert Path(first["artifact_path"]).read_bytes() == Path(second["artifact_path"]).read_bytes()
    assert first["schema_version"] == "tsr-navigation-review-v1"
    assert first["export"] == second["export"]
    assert first["export"]["schema_version"] == "tsr-navigation-review-v1"
    assert first["export"]["summary"] == {
        "annotation_count": 3,
        "frame_count": 2,
        "review_count": 1,
        "video_count": 2,
    }
    assert first["export"]["visited_frame_ids"] == ["camera-a:1", "camera-b:2"]
    assert first["export"]["frames"] == [
        {
            "annotations": [
                earlier_polygon["annotation"],
                earlier_box["annotation"],
            ],
            "frame_index": 1,
            "review": reviewed["review"],
            "review_status": {
                "review_id": reviewed["review_id"],
                "reviewed": True,
                "source": "frame_reviews",
                "status": "reviewed",
            },
            "video_id": "camera-a",
        },
        {
            "annotations": [later_box["annotation"]],
            "frame_index": 2,
            "review": None,
            "review_status": {
                "reviewed": False,
                "source": "default",
                "status": "unreviewed",
            },
            "video_id": "camera-b",
        },
    ]


def test_navigation_review_export_cli_writes_stable_json(tmp_path):
    create_box_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=7,
        label="pedestrian",
        bbox=(1, 2, 3, 4),
    )
    output_path = tmp_path / "review-export.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "export-navigation-review",
            "--project-dir",
            str(tmp_path),
            "--output-path",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = _assert_single_line_json(completed.stdout)
    assert payload["artifact_path"] == str(output_path)
    assert payload["schema_version"] == "tsr-navigation-review-v1"
    assert payload["export"]["schema_version"] == "tsr-navigation-review-v1"
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload["export"]


def test_navigation_review_export_frame_coverage_includes_only_visited_frames(tmp_path):
    total_frames = 1001
    visited_indexes = (0, 17, 1000)

    for frame_index in visited_indexes:
        set_frame_review_status(
            tmp_path,
            video_id="camera-a",
            frame_index=frame_index,
            reviewed=frame_index != 17,
        )

    export = export_navigation_review_artifact(tmp_path, tmp_path / "coverage.json")["export"]

    assert export["summary"]["frame_count"] == len(visited_indexes)
    assert export["visited_frame_ids"] == [f"camera-a:{frame_index}" for frame_index in visited_indexes]
    assert [frame["frame_index"] for frame in export["frames"]] == list(visited_indexes)
    assert "camera-a:1" not in export["visited_frame_ids"]
    assert f"camera-a:{total_frames - 2}" not in export["visited_frame_ids"]


def test_navigation_review_export_includes_review_status_for_each_visited_frame(tmp_path):
    set_frame_review_status(
        tmp_path,
        video_id="camera-a",
        frame_index=0,
        reviewed=True,
    )
    set_frame_review_status(
        tmp_path,
        video_id="camera-a",
        frame_index=1,
        reviewed=False,
    )
    create_box_annotation(
        tmp_path,
        video_id="camera-a",
        frame_index=2,
        label="vehicle",
        bbox=(1, 2, 3, 4),
    )

    export = export_navigation_review_artifact(tmp_path, tmp_path / "review-status-schema.json")["export"]

    assert export["schema_version"] == "tsr-navigation-review-v1"
    assert export["visited_frame_ids"] == ["camera-a:0", "camera-a:1", "camera-a:2"]
    assert [frame["review_status"]["status"] for frame in export["frames"]] == [
        "reviewed",
        "unreviewed",
        "unreviewed",
    ]
    assert [frame["review_status"]["reviewed"] for frame in export["frames"]] == [True, False, False]
    assert [frame["review_status"]["source"] for frame in export["frames"]] == [
        "frame_reviews",
        "frame_reviews",
        "default",
    ]
    for frame in export["frames"]:
        assert set(frame) == {
            "annotations",
            "frame_index",
            "review",
            "review_status",
            "video_id",
        }
        assert set(frame["review_status"]) >= {"reviewed", "source", "status"}
