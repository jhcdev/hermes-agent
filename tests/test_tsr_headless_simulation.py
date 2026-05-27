from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tsr_video_annotation_tool import iter_headless_simulation_ticks, run_headless_simulation


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_headless_simulation_api_executes_exactly_requested_tick_count() -> None:
    result = run_headless_simulation(tick_count=12, total_frames=1001, include_ticks=True)

    assert result["ok"] is True
    assert result["schema_version"] == "tsr-headless-simulation-v1"
    assert result["requested_tick_count"] == 12
    assert result["executed_tick_count"] == 12
    assert result["deterministic"] is True
    assert len(result["ticks"]) == 12
    assert [tick["tick_index"] for tick in result["ticks"]] == list(range(12))
    assert sum(result["command_counts"].values()) == 12
    assert result["trace_artifact"] == {
        "entry_count": 0,
        "format": "jsonl",
        "one_entry_per_tick": True,
        "path": None,
        "schema_version": "tsr-headless-trace-v1",
        "written": False,
    }


def test_headless_simulation_api_is_deterministic_for_same_inputs() -> None:
    first = run_headless_simulation(tick_count=1000, total_frames=1001)
    second = run_headless_simulation(tick_count=1000, total_frames=1001)

    assert first == second
    assert first["requested_tick_count"] == 1000
    assert first["executed_tick_count"] == 1000
    assert "ticks" not in first
    assert sum(first["command_counts"].values()) == 1000


def test_headless_simulation_tick_iterator_streams_exactly_requested_ticks() -> None:
    ticks = list(iter_headless_simulation_ticks(tick_count=7, total_frames=20))

    assert [tick.tick_index for tick in ticks] == list(range(7))
    assert [tick.command for tick in ticks] == [
        "next_frame",
        "next_frame",
        "previous_frame",
        "next_frame",
        "jump_frame",
        "next_frame",
        "next_frame",
    ]


def test_headless_simulation_writes_one_structured_trace_entry_per_tick(tmp_path: Path) -> None:
    trace_path = tmp_path / "headless-trace.jsonl"

    result = run_headless_simulation(tick_count=13, total_frames=1001, trace_path=trace_path)

    assert result["executed_tick_count"] == 13
    assert result["trace_artifact"] == {
        "entry_count": 13,
        "format": "jsonl",
        "one_entry_per_tick": True,
        "path": str(trace_path),
        "schema_version": "tsr-headless-trace-v1",
        "written": True,
    }

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == result["executed_tick_count"]

    records = [json.loads(line) for line in lines]
    assert [record["tick_index"] for record in records] == list(range(13))
    assert all(
        set(record)
        == {
            "after_frame",
            "after_score",
            "before_frame",
            "before_score",
            "command",
            "schema_version",
            "score_delta",
            "scene_transition_direction",
            "scene_transition_distance",
            "scene_transition_event",
            "tick_index",
            "total_frames",
        }
        for record in records
    )
    assert all(record["schema_version"] == "tsr-headless-trace-v1" for record in records)
    assert all(record["total_frames"] == 1001 for record in records)


def test_headless_simulation_trace_records_player_position_changes(tmp_path: Path) -> None:
    trace_path = tmp_path / "player-position-trace.jsonl"

    result = run_headless_simulation(
        tick_count=6,
        total_frames=10,
        start_frame=3,
        trace_path=trace_path,
    )

    assert result["executed_tick_count"] == 6
    trace_records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    expected_ticks = list(
        iter_headless_simulation_ticks(
            tick_count=6,
            total_frames=10,
            start_frame=3,
        )
    )

    assert [
        (record["tick_index"], record["before_frame"], record["after_frame"])
        for record in trace_records
    ] == [
        (tick.tick_index, tick.before_frame, tick.after_frame)
        for tick in expected_ticks
    ]
    assert [record["before_frame"] for record in trace_records] == [3, 4, 5, 4, 5, 8]
    assert [record["after_frame"] for record in trace_records] == [4, 5, 4, 5, 8, 9]
    assert result["final_state"]["current_frame"] == trace_records[-1]["after_frame"]


def test_headless_simulation_trace_records_score_changes_across_simulated_ticks(tmp_path: Path) -> None:
    trace_path = tmp_path / "score-change-trace.jsonl"

    result = run_headless_simulation(
        tick_count=6,
        total_frames=10,
        start_frame=3,
        trace_path=trace_path,
    )

    assert result["executed_tick_count"] == 6
    trace_records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]

    assert [record["score_delta"] for record in trace_records] == [1, 1, -1, 1, 3, 1]
    assert [record["before_score"] for record in trace_records] == [0, 1, 2, 1, 2, 5]
    assert [record["after_score"] for record in trace_records] == [1, 2, 1, 2, 5, 6]
    assert all(
        record["after_score"] - record["before_score"] == record["score_delta"]
        for record in trace_records
    )
    assert trace_records[-1]["after_score"] == sum(record["score_delta"] for record in trace_records)


def test_headless_simulation_trace_records_scene_transition_events_across_ticks(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "scene-transition-trace.jsonl"

    result = run_headless_simulation(
        tick_count=6,
        total_frames=10,
        start_frame=3,
        trace_path=trace_path,
    )

    assert result["executed_tick_count"] == 6
    trace_records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]

    assert [record["scene_transition_event"] for record in trace_records] == [
        "frame_transition",
        "frame_transition",
        "frame_transition",
        "frame_transition",
        "frame_transition",
        "frame_transition",
    ]
    assert [record["scene_transition_direction"] for record in trace_records] == [
        "forward",
        "forward",
        "backward",
        "forward",
        "forward",
        "forward",
    ]
    assert [record["scene_transition_distance"] for record in trace_records] == [1, 1, 1, 1, 3, 1]
    assert all(
        record["scene_transition_distance"] == abs(record["after_frame"] - record["before_frame"])
        for record in trace_records
    )


def test_headless_simulation_trace_artifacts_are_repeatable_for_same_ticks(tmp_path: Path) -> None:
    first_trace_path = tmp_path / "first-headless-trace.jsonl"
    second_trace_path = tmp_path / "second-headless-trace.jsonl"

    first = run_headless_simulation(tick_count=1000, total_frames=1001, trace_path=first_trace_path)
    second = run_headless_simulation(tick_count=1000, total_frames=1001, trace_path=second_trace_path)

    assert first["deterministic_digest"] == second["deterministic_digest"]
    assert first["executed_tick_count"] == second["executed_tick_count"] == 1000
    assert first["trace_artifact"]["entry_count"] == second["trace_artifact"]["entry_count"] == 1000
    assert first_trace_path.read_bytes() == second_trace_path.read_bytes()


def test_headless_simulation_cli_accepts_configurable_tick_count() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "headless-simulate",
            "--ticks",
            "9",
            "--total-frames",
            "1001",
            "--include-ticks",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["requested_tick_count"] == 9
    assert payload["executed_tick_count"] == 9
    assert len(payload["ticks"]) == 9
    assert [tick["tick_index"] for tick in payload["ticks"]] == list(range(9))


def test_headless_simulation_cli_writes_trace_artifact(tmp_path: Path) -> None:
    trace_path = tmp_path / "cli-headless-trace.jsonl"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "headless-simulate",
            "--ticks",
            "9",
            "--total-frames",
            "1001",
            "--trace-path",
            str(trace_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["executed_tick_count"] == 9
    assert payload["trace_artifact"]["path"] == str(trace_path)
    assert payload["trace_artifact"]["entry_count"] == 9
    assert len(trace_path.read_text(encoding="utf-8").splitlines()) == 9


@pytest.mark.parametrize("tick_count", [-1, 1.5])
def test_headless_simulation_rejects_invalid_tick_count(tick_count: int | float) -> None:
    with pytest.raises((TypeError, ValueError)):
        run_headless_simulation(tick_count=tick_count)  # type: ignore[arg-type]
