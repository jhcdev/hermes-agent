"""Frame navigation state for video annotation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FrameNavigationState:
    """Serializable current-frame state with bounded navigation metadata."""

    current_frame: int
    total_frames: int

    def __post_init__(self) -> None:
        if self.total_frames < 1:
            raise ValueError("total_frames must be at least 1")
        if self.current_frame < 0:
            raise ValueError("current_frame must be non-negative")
        if self.current_frame >= self.total_frames:
            raise ValueError("current_frame must be less than total_frames")

    @property
    def has_previous(self) -> bool:
        return self.current_frame > 0

    @property
    def has_next(self) -> bool:
        return self.current_frame < self.total_frames - 1

    @property
    def at_start(self) -> bool:
        return self.current_frame == 0

    @property
    def at_end(self) -> bool:
        return self.current_frame == self.total_frames - 1

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "current_frame": self.current_frame,
            "total_frames": self.total_frames,
            "has_previous": self.has_previous,
            "has_next": self.has_next,
            "at_start": self.at_start,
            "at_end": self.at_end,
        }


def next_frame_state(state: FrameNavigationState) -> FrameNavigationState:
    """Move one frame forward, clamping at the final frame."""

    if not state.has_next:
        return state
    return FrameNavigationState(
        current_frame=state.current_frame + 1,
        total_frames=state.total_frames,
    )


def previous_frame_state(state: FrameNavigationState) -> FrameNavigationState:
    """Move one frame backward, clamping at the first frame."""

    if not state.has_previous:
        return state
    return FrameNavigationState(
        current_frame=state.current_frame - 1,
        total_frames=state.total_frames,
    )


def jump_to_frame_state(state: FrameNavigationState, frame_index: int) -> FrameNavigationState:
    """Jump to a specific frame index and return bounded current-frame state."""

    if not isinstance(frame_index, int):
        raise TypeError("frame_index must be an integer")
    if frame_index < 0 or frame_index >= state.total_frames:
        raise ValueError("frame_index must be within the available frame range")
    if frame_index == state.current_frame:
        return state
    return FrameNavigationState(
        current_frame=frame_index,
        total_frames=state.total_frames,
    )


def handle_frame_navigation_command(
    state: FrameNavigationState,
    command: str,
    *,
    frame_index: int | None = None,
) -> dict[str, Any]:
    """Run a frame navigation command and return stable current-frame state."""

    normalized = command.strip().lower().replace("-", "_")
    if normalized in {"next", "next_frame"}:
        return next_frame_state(state).to_dict()
    if normalized in {"previous", "previous_frame", "prev", "prev_frame"}:
        return previous_frame_state(state).to_dict()
    if normalized in {"jump", "jump_frame", "go_to_frame", "goto_frame"}:
        if frame_index is None:
            raise ValueError("frame_index is required for jump frame navigation")
        return jump_to_frame_state(state, frame_index).to_dict()
    raise ValueError(f"unsupported frame navigation command: {command}")
