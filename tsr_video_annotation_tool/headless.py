from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

from agent.video_annotation.navigation import (
    FrameNavigationState,
    handle_frame_navigation_command,
)


HEADLESS_SIMULATION_SCHEMA_VERSION = "tsr-headless-simulation-v1"
HEADLESS_TRACE_SCHEMA_VERSION = "tsr-headless-trace-v1"


@dataclass(frozen=True, slots=True)
class HeadlessInputTick:
    """One deterministic input tick produced by the headless simulator."""

    tick_index: int
    command: str
    before_frame: int
    after_frame: int
    before_score: int
    after_score: int
    score_delta: int

    def to_json_record(self) -> dict[str, int | str]:
        return asdict(self)

    def to_trace_record(self, *, total_frames: int) -> dict[str, int | str | bool]:
        record = self.to_json_record()
        record["schema_version"] = HEADLESS_TRACE_SCHEMA_VERSION
        record["total_frames"] = total_frames
        record["scene_transition_event"] = (
            "frame_transition" if self.before_frame != self.after_frame else "frame_hold"
        )
        record["scene_transition_direction"] = _scene_transition_direction(
            self.before_frame,
            self.after_frame,
        )
        record["scene_transition_distance"] = abs(self.after_frame - self.before_frame)
        return record


def iter_headless_simulation_ticks(
    *,
    tick_count: int,
    total_frames: int = 1001,
    start_frame: int = 0,
) -> Iterator[HeadlessInputTick]:
    """Yield exactly ``tick_count`` deterministic navigation input ticks."""

    requested_ticks = _validate_non_negative_int("tick_count", tick_count)
    state = FrameNavigationState(
        current_frame=_validate_non_negative_int("start_frame", start_frame),
        total_frames=_validate_positive_int("total_frames", total_frames),
    )
    score = 0

    for tick_index in range(requested_ticks):
        command, frame_index = _deterministic_input_for_tick(tick_index, state.total_frames)
        before_frame = state.current_frame
        before_score = score
        next_state = handle_frame_navigation_command(state, command, frame_index=frame_index)
        state = FrameNavigationState(
            current_frame=int(next_state["current_frame"]),
            total_frames=int(next_state["total_frames"]),
        )
        score_delta = state.current_frame - before_frame
        score += score_delta
        yield HeadlessInputTick(
            tick_index=tick_index,
            command=command,
            before_frame=before_frame,
            after_frame=state.current_frame,
            before_score=before_score,
            after_score=score,
            score_delta=score_delta,
        )


def run_headless_simulation(
    *,
    tick_count: int,
    total_frames: int = 1001,
    start_frame: int = 0,
    include_ticks: bool = False,
    trace_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run a deterministic headless navigation simulation."""

    requested_ticks = _validate_non_negative_int("tick_count", tick_count)
    validated_total_frames = _validate_positive_int("total_frames", total_frames)
    command_counts = {"jump_frame": 0, "next_frame": 0, "previous_frame": 0}
    digest = hashlib.sha256()
    final_frame = _validate_non_negative_int("start_frame", start_frame)
    tick_log: list[dict[str, int | str]] = []
    trace_writer = _HeadlessTraceWriter(trace_path)

    try:
        for tick in iter_headless_simulation_ticks(
            tick_count=requested_ticks,
            total_frames=validated_total_frames,
            start_frame=start_frame,
        ):
            record = tick.to_json_record()
            command_counts[tick.command] += 1
            final_frame = tick.after_frame
            digest.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            digest.update(b"\n")
            trace_writer.write_tick(tick, total_frames=validated_total_frames)
            if include_ticks:
                tick_log.append(record)
    except Exception:
        trace_writer.abort()
        raise
    else:
        trace_writer.commit()

    result: dict[str, Any] = {
        "ok": True,
        "schema_version": HEADLESS_SIMULATION_SCHEMA_VERSION,
        "requested_tick_count": requested_ticks,
        "executed_tick_count": requested_ticks,
        "deterministic": True,
        "deterministic_digest": digest.hexdigest(),
        "command_counts": command_counts,
        "final_state": FrameNavigationState(
            current_frame=final_frame,
            total_frames=validated_total_frames,
        ).to_dict(),
        "trace_artifact": trace_writer.to_result(),
    }
    if include_ticks:
        result["ticks"] = tick_log
    return result


class _HeadlessTraceWriter:
    """Stream a tick trace to JSONL without retaining records in memory."""

    def __init__(self, trace_path: str | Path | None) -> None:
        self._target_path = Path(trace_path) if trace_path is not None else None
        self._temp_path: Path | None = None
        self._file: Any | None = None
        self._entry_count = 0
        if self._target_path is None:
            return

        self._target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=self._target_path.parent,
            prefix=f".{self._target_path.name}.",
            suffix=".tmp",
        )
        self._file = temp_file
        self._temp_path = Path(temp_file.name)

    def write_tick(self, tick: HeadlessInputTick, *, total_frames: int) -> None:
        if self._file is None:
            return
        payload = tick.to_trace_record(total_frames=total_frames)
        self._file.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        self._file.write("\n")
        self._entry_count += 1

    def commit(self) -> None:
        if self._file is None or self._target_path is None or self._temp_path is None:
            return
        self._file.close()
        os.replace(self._temp_path, self._target_path)
        self._temp_path = None
        self._file = None

    def abort(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._temp_path is not None:
            try:
                self._temp_path.unlink()
            except FileNotFoundError:
                pass
            self._temp_path = None

    def to_result(self) -> dict[str, Any]:
        return {
            "entry_count": self._entry_count,
            "format": "jsonl",
            "one_entry_per_tick": True,
            "path": str(self._target_path) if self._target_path is not None else None,
            "schema_version": HEADLESS_TRACE_SCHEMA_VERSION,
            "written": self._target_path is not None,
        }


def _deterministic_input_for_tick(tick_index: int, total_frames: int) -> tuple[str, int | None]:
    phase = tick_index % 5
    if phase in {0, 1, 3}:
        return "next_frame", None
    if phase == 2:
        return "previous_frame", None
    return "jump_frame", (tick_index * 17) % total_frames


def _scene_transition_direction(before_frame: int, after_frame: int) -> str:
    if after_frame > before_frame:
        return "forward"
    if after_frame < before_frame:
        return "backward"
    return "none"


def _validate_non_negative_int(name: str, value: int) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _validate_positive_int(name: str, value: int) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value
