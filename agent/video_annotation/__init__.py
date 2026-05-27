"""Core primitives for the TSR video annotation prototypes."""

from agent.video_annotation.navigation import (
    FrameNavigationState,
    handle_frame_navigation_command,
    jump_to_frame_state,
    next_frame_state,
    previous_frame_state,
)

__all__ = [
    "FrameNavigationState",
    "handle_frame_navigation_command",
    "jump_to_frame_state",
    "next_frame_state",
    "previous_frame_state",
]
