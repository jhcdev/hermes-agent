from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator

from tsr_video_annotation_tool import (
    FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA,
    aggregate_frame_transition_latency,
    handle_frame_transition_benchmark_command,
    run_frame_transition_benchmark,
    validate_frame_transition_benchmark_response,
)
from tsr_video_annotation_tool.benchmark import FrameTransitionLatencySample


class _FakeTimer:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class _FrameStream:
    def __init__(self, frame_count: int) -> None:
        self.iterated_frames: list[int] = []
        self._frame_count = frame_count

    def __iter__(self) -> Iterator[dict[str, int]]:
        for frame_index in range(self._frame_count):
            self.iterated_frames.append(frame_index)
            yield {"frame_index": frame_index}


def test_frame_transition_benchmark_collects_latency_samples_for_adjacent_frames() -> None:
    transitions: list[tuple[int, int]] = []

    def transition(previous: dict[str, int], current: dict[str, int]) -> None:
        transitions.append((previous["frame_index"], current["frame_index"]))

    result = run_frame_transition_benchmark(
        [{"frame_index": 10}, {"frame_index": 11}, {"frame_index": 12}],
        transition=transition,
        timer=_FakeTimer([1.0, 1.0125, 2.0, 2.003]),
    )

    assert result == {
        "ok": True,
        "schema_version": "tsr-frame-transition-benchmark-v1",
        "benchmark": {
            "name": "frame_transition_latency",
            "description": "Latency for adjacent frame transitions in a streaming frame sequence.",
        },
        "metadata": {
            "frame_count": 3,
            "transition_count": 2,
            "timing_unit": "ms",
            "latency_sample_count": 2,
            "streaming": True,
            "transition_callback": True,
        },
        "summary": {"transition_count": 2, "frame_transition_p95_ms": 12.5},
        "samples": [
            {
                "transition_index": 0,
                "from_frame_id": "10",
                "to_frame_id": "11",
                "latency_ms": 12.5,
            },
            {
                "transition_index": 1,
                "from_frame_id": "11",
                "to_frame_id": "12",
                "latency_ms": 3.0,
            },
        ],
    }
    assert validate_frame_transition_benchmark_response(result) == {
        "ok": True,
        "schema_version": "tsr-frame-transition-benchmark-v1",
        "schema_id": FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA["$id"],
        "errors": [],
    }
    assert transitions == [(10, 11), (11, 12)]


def test_frame_transition_benchmark_streams_controlled_sequence_without_len_or_indexing() -> None:
    stream = _FrameStream(frame_count=1001)
    result = run_frame_transition_benchmark(
        stream,
        timer=_FakeTimer([value / 1000 for value in range(2000)]),
    )

    assert stream.iterated_frames == list(range(1001))
    assert result["metadata"] == {
        "frame_count": 1001,
        "transition_count": 1000,
        "timing_unit": "ms",
        "latency_sample_count": 1000,
        "streaming": True,
        "transition_callback": False,
    }
    assert result["summary"] == {"transition_count": 1000, "frame_transition_p95_ms": 1.0}
    assert result["samples"][0] == {
        "transition_index": 0,
        "from_frame_id": "0",
        "to_frame_id": "1",
        "latency_ms": 1.0,
    }
    assert result["samples"][-1] == {
        "transition_index": 999,
        "from_frame_id": "999",
        "to_frame_id": "1000",
        "latency_ms": 1.0,
    }


def test_frame_transition_benchmark_api_invokes_controlled_json_sequence() -> None:
    result = handle_frame_transition_benchmark_command(
        json.dumps(
            [
                {"frame_id": "camera-a:000010"},
                {"frame_id": "camera-a:000011"},
                {"frame_id": "camera-a:000013"},
            ]
        )
    )

    assert result["ok"] is True
    assert validate_frame_transition_benchmark_response(result)["ok"] is True
    assert result["summary"]["transition_count"] == 2
    assert isinstance(result["summary"]["frame_transition_p95_ms"], float)
    assert [(sample["from_frame_id"], sample["to_frame_id"]) for sample in result["samples"]] == [
        ("camera-a:000010", "camera-a:000011"),
        ("camera-a:000011", "camera-a:000013"),
    ]


def test_frame_transition_benchmark_cli_invokes_controlled_sequence() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tsr_video_annotation_tool.cli",
            "benchmark-frame-transitions",
            "--frame-sequence",
            json.dumps([{"frame_index": 7}, {"frame_index": 8}, {"frame_index": 9}]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == "tsr-frame-transition-benchmark-v1"
    assert validate_frame_transition_benchmark_response(payload)["ok"] is True
    assert payload["metadata"] == {
        "frame_count": 3,
        "transition_count": 2,
        "timing_unit": "ms",
        "latency_sample_count": 2,
        "streaming": True,
        "transition_callback": False,
    }
    assert payload["summary"]["transition_count"] == 2
    assert isinstance(payload["summary"]["frame_transition_p95_ms"], float)
    assert [(sample["from_frame_id"], sample["to_frame_id"]) for sample in payload["samples"]] == [
        ("7", "8"),
        ("8", "9"),
    ]


def test_frame_transition_benchmark_empty_or_single_frame_has_no_transitions() -> None:
    empty = run_frame_transition_benchmark([], timer=_FakeTimer([]))
    single = run_frame_transition_benchmark(["only"], timer=_FakeTimer([]))

    assert empty["summary"] == {"transition_count": 0, "frame_transition_p95_ms": None}
    assert empty["metadata"]["frame_count"] == 0
    assert validate_frame_transition_benchmark_response(empty)["ok"] is True
    assert single["summary"] == {"transition_count": 0, "frame_transition_p95_ms": None}
    assert single["metadata"]["frame_count"] == 1
    assert validate_frame_transition_benchmark_response(single)["ok"] is True


def test_frame_transition_latency_sample_is_json_record() -> None:
    sample = FrameTransitionLatencySample(
        transition_index=4,
        from_frame_id="camera-a:4",
        to_frame_id="camera-a:5",
        latency_ms=7.25,
    )

    assert sample.to_json_record() == {
        "transition_index": 4,
        "from_frame_id": "camera-a:4",
        "to_frame_id": "camera-a:5",
        "latency_ms": 7.25,
    }


def test_frame_transition_benchmark_schema_documents_samples_and_metadata() -> None:
    assert FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA["required"] == [
        "ok",
        "schema_version",
        "benchmark",
        "metadata",
        "summary",
        "samples",
    ]
    assert set(FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA["properties"]["metadata"]["required"]) == {
        "frame_count",
        "transition_count",
        "timing_unit",
        "latency_sample_count",
        "streaming",
        "transition_callback",
    }
    assert FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA["properties"]["summary"]["required"] == [
        "transition_count",
        "frame_transition_p95_ms",
    ]
    assert FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA["properties"]["samples"]["items"]["required"] == [
        "transition_index",
        "from_frame_id",
        "to_frame_id",
        "latency_ms",
    ]


def test_frame_transition_benchmark_validator_rejects_inconsistent_counts() -> None:
    result = run_frame_transition_benchmark(
        [{"frame_index": 0}, {"frame_index": 1}],
        timer=_FakeTimer([1.0, 1.002]),
    )
    result["metadata"]["latency_sample_count"] = 7

    validation = validate_frame_transition_benchmark_response(result)

    assert validation["ok"] is False
    assert validation["errors"] == ["metadata.latency_sample_count must match samples length"]


def test_latency_aggregation_computes_nearest_rank_p95_deterministically() -> None:
    samples = [{"latency_ms": value} for value in [5.0, 1.0, 100.0, 8.0, 3.0]]

    assert aggregate_frame_transition_latency(samples) == {
        "transition_count": 5,
        "frame_transition_p95_ms": 100.0,
    }
    assert aggregate_frame_transition_latency(list(reversed(samples))) == {
        "transition_count": 5,
        "frame_transition_p95_ms": 100.0,
    }


def test_latency_aggregation_handles_empty_single_and_exact_rank_edges() -> None:
    assert aggregate_frame_transition_latency([]) == {
        "transition_count": 0,
        "frame_transition_p95_ms": None,
    }
    assert aggregate_frame_transition_latency([{"latency_ms": 7.1234564}]) == {
        "transition_count": 1,
        "frame_transition_p95_ms": 7.123456,
    }
    assert aggregate_frame_transition_latency([{"latency_ms": value} for value in range(1, 101)]) == {
        "transition_count": 100,
        "frame_transition_p95_ms": 95.0,
    }


def test_latency_aggregation_rejects_invalid_latency_samples() -> None:
    for samples in (
        [{"latency_ms": -1}],
        [{"latency_ms": float("nan")}],
        [{"latency_ms": True}],
        [{"not_latency": 1}],
    ):
        try:
            aggregate_frame_transition_latency(samples)
        except ValueError as exc:
            assert str(exc) == "latency sample must include finite non-negative latency_ms"
        else:
            raise AssertionError("invalid latency sample should fail aggregation")


def test_frame_transition_benchmark_validator_rejects_wrong_p95_summary() -> None:
    result = run_frame_transition_benchmark(
        [{"frame_index": 0}, {"frame_index": 1}, {"frame_index": 2}],
        timer=_FakeTimer([1.0, 1.002, 2.0, 2.007]),
    )
    result["summary"]["frame_transition_p95_ms"] = 2.0

    validation = validate_frame_transition_benchmark_response(result)

    assert validation["ok"] is False
    assert validation["errors"] == ["summary.frame_transition_p95_ms must match samples p95"]
