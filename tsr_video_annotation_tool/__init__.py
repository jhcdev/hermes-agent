"""Core APIs for the TSR video annotation prototype."""

from tsr_video_annotation_tool.annotations import (
    BoxAnnotation,
    FrameReviewStatus,
    PolygonAnnotation,
    assign_annotation_class,
    create_box_annotation,
    create_polygon_annotation,
    export_navigation_review_artifact,
    handle_frame_review_command,
    iter_box_annotations,
    iter_frame_review_statuses,
    iter_polygon_annotations,
    load_box_annotation,
    load_frame_review_status,
    load_polygon_annotation,
    set_frame_review_status,
)
from tsr_video_annotation_tool.benchmark import (
    FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA,
    FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION,
    FrameTransitionLatencySample,
    aggregate_frame_transition_latency,
    handle_frame_transition_benchmark_command,
    run_frame_transition_benchmark,
    validate_frame_transition_benchmark_response,
)
from tsr_video_annotation_tool.headless import (
    HeadlessInputTick,
    iter_headless_simulation_ticks,
    run_headless_simulation,
)
from tsr_video_annotation_tool.metadata import (
    DatasetMetadata,
    load_dataset_metadata,
    run_metadata_loading_check,
)
from tsr_video_annotation_tool.public_contract import run_public_contract_check

__all__ = [
    "BoxAnnotation",
    "DatasetMetadata",
    "FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA",
    "FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION",
    "FrameReviewStatus",
    "FrameTransitionLatencySample",
    "HeadlessInputTick",
    "PolygonAnnotation",
    "aggregate_frame_transition_latency",
    "assign_annotation_class",
    "create_box_annotation",
    "create_polygon_annotation",
    "export_navigation_review_artifact",
    "handle_frame_review_command",
    "handle_frame_transition_benchmark_command",
    "iter_box_annotations",
    "iter_frame_review_statuses",
    "iter_headless_simulation_ticks",
    "iter_polygon_annotations",
    "load_box_annotation",
    "load_dataset_metadata",
    "load_frame_review_status",
    "load_polygon_annotation",
    "run_frame_transition_benchmark",
    "run_headless_simulation",
    "run_launch_check",
    "run_metadata_loading_check",
    "run_public_contract_check",
    "set_frame_review_status",
    "validate_frame_transition_benchmark_response",
]


def __getattr__(name: str) -> object:
    if name == "run_launch_check":
        from tsr_video_annotation_tool.launch_check import run_launch_check

        globals()[name] = run_launch_check
        return run_launch_check
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
