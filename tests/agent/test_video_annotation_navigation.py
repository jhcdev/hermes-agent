from __future__ import annotations

import pytest

from agent.video_annotation.navigation import (
    FrameNavigationState,
    handle_frame_navigation_command,
    jump_to_frame_state,
    previous_frame_state,
)


def test_next_frame_from_start_returns_stable_current_frame_state() -> None:
    result = handle_frame_navigation_command(
        FrameNavigationState(current_frame=0, total_frames=1001),
        "next_frame",
    )

    assert result == {
        "current_frame": 1,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": True,
        "at_start": False,
        "at_end": False,
    }


def test_next_frame_from_middle_returns_stable_current_frame_state() -> None:
    result = handle_frame_navigation_command(
        FrameNavigationState(current_frame=500, total_frames=1001),
        "next",
    )

    assert result == {
        "current_frame": 501,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": True,
        "at_start": False,
        "at_end": False,
    }


def test_next_frame_at_end_stays_on_final_frame() -> None:
    result = handle_frame_navigation_command(
        FrameNavigationState(current_frame=1000, total_frames=1001),
        "next_frame",
    )

    assert result == {
        "current_frame": 1000,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": False,
        "at_start": False,
        "at_end": True,
    }


def test_previous_frame_from_start_returns_stable_current_frame_state() -> None:
    result = handle_frame_navigation_command(
        FrameNavigationState(current_frame=0, total_frames=1001),
        "previous_frame",
    )

    assert result == {
        "current_frame": 0,
        "total_frames": 1001,
        "has_previous": False,
        "has_next": True,
        "at_start": True,
        "at_end": False,
    }


def test_previous_frame_from_middle_returns_stable_current_frame_state() -> None:
    result = handle_frame_navigation_command(
        FrameNavigationState(current_frame=500, total_frames=1001),
        "prev",
    )

    assert result == {
        "current_frame": 499,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": True,
        "at_start": False,
        "at_end": False,
    }


def test_previous_frame_from_end_returns_stable_current_frame_state() -> None:
    result = handle_frame_navigation_command(
        FrameNavigationState(current_frame=1000, total_frames=1001),
        "previous",
    )

    assert result == {
        "current_frame": 999,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": True,
        "at_start": False,
        "at_end": False,
    }


def test_previous_frame_api_from_start_reuses_stable_state() -> None:
    state = FrameNavigationState(current_frame=0, total_frames=1001)

    assert previous_frame_state(state) is state
    assert previous_frame_state(state).to_dict() == {
        "current_frame": 0,
        "total_frames": 1001,
        "has_previous": False,
        "has_next": True,
        "at_start": True,
        "at_end": False,
    }


def test_jump_frame_api_returns_stable_current_frame_state_for_valid_index() -> None:
    result = jump_to_frame_state(
        FrameNavigationState(current_frame=500, total_frames=1001),
        1000,
    )

    assert result.to_dict() == {
        "current_frame": 1000,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": False,
        "at_start": False,
        "at_end": True,
    }


def test_jump_frame_command_returns_stable_current_frame_state_for_valid_index() -> None:
    result = handle_frame_navigation_command(
        FrameNavigationState(current_frame=500, total_frames=1001),
        "jump-frame",
        frame_index=0,
    )

    assert result == {
        "current_frame": 0,
        "total_frames": 1001,
        "has_previous": False,
        "has_next": True,
        "at_start": True,
        "at_end": False,
    }


def test_jump_frame_api_reuses_state_when_index_is_current_frame() -> None:
    state = FrameNavigationState(current_frame=123, total_frames=1001)

    assert jump_to_frame_state(state, 123) is state
    assert jump_to_frame_state(state, 123).to_dict() == {
        "current_frame": 123,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": True,
        "at_start": False,
        "at_end": False,
    }


@pytest.mark.parametrize("frame_index", [-1, 1001])
def test_jump_frame_api_rejects_out_of_range_indexes(frame_index: int) -> None:
    state = FrameNavigationState(current_frame=500, total_frames=1001)

    with pytest.raises(ValueError):
        jump_to_frame_state(state, frame_index)

    assert state.to_dict() == {
        "current_frame": 500,
        "total_frames": 1001,
        "has_previous": True,
        "has_next": True,
        "at_start": False,
        "at_end": False,
    }


def test_jump_frame_command_requires_frame_index() -> None:
    with pytest.raises(ValueError):
        handle_frame_navigation_command(
            FrameNavigationState(current_frame=500, total_frames=1001),
            "goto_frame",
        )


@pytest.mark.parametrize(
    ("current_frame", "total_frames"),
    [(-1, 1001), (1001, 1001), (0, 0)],
)
def test_frame_navigation_state_rejects_invalid_bounds(
    current_frame: int,
    total_frames: int,
) -> None:
    with pytest.raises(ValueError):
        FrameNavigationState(current_frame=current_frame, total_frames=total_frames)
