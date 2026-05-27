from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Sequence


FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION = "tsr-frame-transition-benchmark-v1"
FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nousresearch.github.io/hermes-agent/schemas/tsr-frame-transition-benchmark-v1.json",
    "title": "TSR frame transition benchmark response",
    "type": "object",
    "additionalProperties": False,
    "required": ["ok", "schema_version", "benchmark", "metadata", "summary", "samples"],
    "properties": {
        "ok": {"type": "boolean"},
        "schema_version": {"const": FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION},
        "benchmark": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "description"],
            "properties": {
                "name": {"const": "frame_transition_latency"},
                "description": {"type": "string", "minLength": 1},
            },
        },
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "frame_count",
                "transition_count",
                "timing_unit",
                "latency_sample_count",
                "streaming",
                "transition_callback",
            ],
            "properties": {
                "frame_count": {"type": "integer", "minimum": 0},
                "transition_count": {"type": "integer", "minimum": 0},
                "timing_unit": {"const": "ms"},
                "latency_sample_count": {"type": "integer", "minimum": 0},
                "streaming": {"const": True},
                "transition_callback": {"type": "boolean"},
            },
        },
        "summary": {
            "type": "object",
            "additionalProperties": False,
            "required": ["transition_count", "frame_transition_p95_ms"],
            "properties": {
                "transition_count": {"type": "integer", "minimum": 0},
                "frame_transition_p95_ms": {
                    "anyOf": [
                        {"type": "number", "minimum": 0},
                        {"type": "null"},
                    ]
                },
            },
        },
        "samples": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["transition_index", "from_frame_id", "to_frame_id", "latency_ms"],
                "properties": {
                    "transition_index": {"type": "integer", "minimum": 0},
                    "from_frame_id": {"type": "string"},
                    "to_frame_id": {"type": "string"},
                    "latency_ms": {"type": "number", "minimum": 0},
                },
            },
        },
    },
}
_MISSING = object()


@dataclass(frozen=True)
class FrameTransitionLatencySample:
    """Timing sample for one adjacent frame transition."""

    transition_index: int
    from_frame_id: str
    to_frame_id: str
    latency_ms: float

    def to_json_record(self) -> dict[str, Any]:
        return asdict(self)


def run_frame_transition_benchmark(
    frame_sequence: Iterable[Any],
    *,
    transition: Callable[[Any, Any], Any] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """Iterate over frames and collect latency samples for adjacent transitions.

    The runner is deliberately streaming: it keeps only the previous and current
    frame in memory, so the same function can validate 1000+ frame projects
    without materializing the whole sequence.
    """

    frame_iterator = iter(frame_sequence)
    previous = next(frame_iterator, _MISSING)
    if previous is _MISSING:
        return _benchmark_result([], frame_count=0, transition_callback=transition is not None)

    samples: list[dict[str, Any]] = []
    frame_count = 1
    for transition_index, current in enumerate(frame_iterator):
        frame_count += 1
        started_at = timer()
        if transition is not None:
            transition(previous, current)
        finished_at = timer()

        samples.append(
            FrameTransitionLatencySample(
                transition_index=transition_index,
                from_frame_id=_frame_identifier(previous),
                to_frame_id=_frame_identifier(current),
                latency_ms=round((finished_at - started_at) * 1000.0, 6),
            ).to_json_record()
        )
        previous = current

    return _benchmark_result(samples, frame_count=frame_count, transition_callback=transition is not None)


def handle_frame_transition_benchmark_command(frame_sequence_json: str) -> dict[str, Any]:
    """Run the frame-transition benchmark from a controlled JSON frame sequence."""

    frame_sequence = _parse_controlled_frame_sequence(frame_sequence_json)
    return run_frame_transition_benchmark(frame_sequence)


def validate_frame_transition_benchmark_response(response: dict[str, Any]) -> dict[str, Any]:
    """Validate a frame-transition benchmark response against the documented schema.

    The returned report is JSON-serializable so benchmark callers can gate CI or
    ingestion without importing a JSON Schema runtime.
    """

    errors: list[str] = []
    _validate_response_object(response, errors)
    return {
        "ok": not errors,
        "schema_version": FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION,
        "schema_id": FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA["$id"],
        "errors": errors,
    }


def aggregate_frame_transition_latency(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Compute deterministic latency summary fields from benchmark samples.

    p95 uses the nearest-rank method: sort all observed transition latencies,
    then select ``ceil(0.95 * n)`` with one-based indexing. This matches common
    latency SLO reporting and avoids interpolation-dependent drift.
    """

    latencies = [_sample_latency_ms(sample) for sample in samples]
    return {
        "transition_count": len(latencies),
        "frame_transition_p95_ms": _nearest_rank_percentile(latencies, 0.95),
    }


def _benchmark_result(
    samples: list[dict[str, Any]],
    *,
    frame_count: int,
    transition_callback: bool,
) -> dict[str, Any]:
    transition_count = len(samples)
    return {
        "ok": True,
        "schema_version": FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION,
        "benchmark": {
            "name": "frame_transition_latency",
            "description": "Latency for adjacent frame transitions in a streaming frame sequence.",
        },
        "metadata": {
            "frame_count": frame_count,
            "transition_count": transition_count,
            "timing_unit": "ms",
            "latency_sample_count": transition_count,
            "streaming": True,
            "transition_callback": transition_callback,
        },
        "summary": aggregate_frame_transition_latency(samples),
        "samples": samples,
    }


def _validate_response_object(response: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(response, dict):
        errors.append("response must be an object")
        return

    expected_keys = {"ok", "schema_version", "benchmark", "metadata", "summary", "samples"}
    _validate_exact_keys(response, expected_keys, "response", errors)
    _validate_bool(response.get("ok"), "ok", errors)
    if response.get("schema_version") != FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION:
        errors.append("schema_version must be tsr-frame-transition-benchmark-v1")

    _validate_benchmark(response.get("benchmark"), errors)
    metadata = response.get("metadata")
    summary = response.get("summary")
    samples = response.get("samples")
    _validate_metadata(metadata, errors)
    _validate_summary(summary, errors)
    _validate_samples(samples, errors)

    if isinstance(metadata, dict) and isinstance(summary, dict) and isinstance(samples, list):
        transition_count = len(samples)
        if metadata.get("latency_sample_count") != transition_count:
            errors.append("metadata.latency_sample_count must match samples length")
        if metadata.get("transition_count") != transition_count:
            errors.append("metadata.transition_count must match samples length")
        if summary.get("transition_count") != transition_count:
            errors.append("summary.transition_count must match samples length")
        expected_p95 = aggregate_frame_transition_latency(samples)["frame_transition_p95_ms"]
        if summary.get("frame_transition_p95_ms") != expected_p95:
            errors.append("summary.frame_transition_p95_ms must match samples p95")
        expected_minimum_frames = 0 if transition_count == 0 else transition_count + 1
        if isinstance(metadata.get("frame_count"), int) and metadata["frame_count"] < expected_minimum_frames:
            errors.append("metadata.frame_count must cover all sampled transitions")


def _validate_benchmark(benchmark: Any, errors: list[str]) -> None:
    if not isinstance(benchmark, dict):
        errors.append("benchmark must be an object")
        return
    _validate_exact_keys(benchmark, {"name", "description"}, "benchmark", errors)
    if benchmark.get("name") != "frame_transition_latency":
        errors.append("benchmark.name must be frame_transition_latency")
    if not isinstance(benchmark.get("description"), str) or not benchmark["description"]:
        errors.append("benchmark.description must be a non-empty string")


def _validate_metadata(metadata: Any, errors: list[str]) -> None:
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
        return
    _validate_exact_keys(
        metadata,
        {
            "frame_count",
            "transition_count",
            "timing_unit",
            "latency_sample_count",
            "streaming",
            "transition_callback",
        },
        "metadata",
        errors,
    )
    _validate_non_negative_int(metadata.get("frame_count"), "metadata.frame_count", errors)
    _validate_non_negative_int(metadata.get("transition_count"), "metadata.transition_count", errors)
    _validate_non_negative_int(metadata.get("latency_sample_count"), "metadata.latency_sample_count", errors)
    if metadata.get("timing_unit") != "ms":
        errors.append("metadata.timing_unit must be ms")
    if metadata.get("streaming") is not True:
        errors.append("metadata.streaming must be true")
    _validate_bool(metadata.get("transition_callback"), "metadata.transition_callback", errors)


def _validate_summary(summary: Any, errors: list[str]) -> None:
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
        return
    _validate_exact_keys(summary, {"transition_count", "frame_transition_p95_ms"}, "summary", errors)
    _validate_non_negative_int(summary.get("transition_count"), "summary.transition_count", errors)
    p95 = summary.get("frame_transition_p95_ms")
    if p95 is not None:
        _validate_non_negative_number(p95, "summary.frame_transition_p95_ms", errors)


def _validate_samples(samples: Any, errors: list[str]) -> None:
    if not isinstance(samples, list):
        errors.append("samples must be an array")
        return
    for index, sample in enumerate(samples):
        path = f"samples[{index}]"
        if not isinstance(sample, dict):
            errors.append(f"{path} must be an object")
            continue
        _validate_exact_keys(
            sample,
            {"transition_index", "from_frame_id", "to_frame_id", "latency_ms"},
            path,
            errors,
        )
        _validate_non_negative_int(sample.get("transition_index"), f"{path}.transition_index", errors)
        if sample.get("transition_index") != index:
            errors.append(f"{path}.transition_index must match sample position")
        if not isinstance(sample.get("from_frame_id"), str):
            errors.append(f"{path}.from_frame_id must be a string")
        if not isinstance(sample.get("to_frame_id"), str):
            errors.append(f"{path}.to_frame_id must be a string")
        _validate_non_negative_number(sample.get("latency_ms"), f"{path}.latency_ms", errors)


def _validate_exact_keys(payload: dict[str, Any], expected_keys: set[str], path: str, errors: list[str]) -> None:
    actual_keys = set(payload)
    missing = sorted(expected_keys - actual_keys)
    extra = sorted(actual_keys - expected_keys)
    if missing:
        errors.append(f"{path} missing keys: {', '.join(missing)}")
    if extra:
        errors.append(f"{path} has unexpected keys: {', '.join(extra)}")


def _validate_bool(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, bool):
        errors.append(f"{path} must be a boolean")


def _validate_non_negative_int(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append(f"{path} must be a non-negative integer")


def _validate_non_negative_number(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0 or not math.isfinite(value):
        errors.append(f"{path} must be a non-negative number")


def _frame_identifier(frame: Any) -> str:
    if isinstance(frame, dict):
        for key in ("frame_id", "id", "frame_index"):
            if key in frame:
                return str(frame[key])
    return str(frame)


def _parse_controlled_frame_sequence(frame_sequence_json: str) -> Iterable[Any]:
    try:
        frame_sequence = json.loads(frame_sequence_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"frame sequence must be valid JSON: {exc.msg}") from exc

    if not isinstance(frame_sequence, list):
        raise ValueError("frame sequence must be a JSON array")

    return frame_sequence


def _sample_latency_ms(sample: dict[str, Any]) -> float:
    if not isinstance(sample, dict):
        raise ValueError("latency sample must be an object")
    latency = sample.get("latency_ms")
    if not isinstance(latency, int | float) or isinstance(latency, bool) or latency < 0 or not math.isfinite(latency):
        raise ValueError("latency sample must include finite non-negative latency_ms")
    return float(latency)


def _nearest_rank_percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(percentile * len(ordered))
    return round(ordered[rank - 1], 6)
