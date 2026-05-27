from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tsr_video_annotation_tool.annotations import (
    assign_annotation_class,
    create_box_annotation,
    create_polygon_annotation,
    export_navigation_review_artifact,
    handle_frame_review_command,
)
from tsr_video_annotation_tool.benchmark import handle_frame_transition_benchmark_command
from tsr_video_annotation_tool.headless import run_headless_simulation
from tsr_video_annotation_tool.launch_check import run_launch_check
from tsr_video_annotation_tool.main_loop import run_annotation_main_loop
from tsr_video_annotation_tool.metadata import run_metadata_loading_check
from tsr_video_annotation_tool.public_contract import run_public_contract_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tsr-annotate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    box_parser = subparsers.add_parser("create-box", help="Create or replace a box annotation")
    box_parser.add_argument("--project-dir", required=True, type=Path)
    box_parser.add_argument("--video-id", required=True)
    box_parser.add_argument("--frame-index", required=True, type=int)
    box_parser.add_argument("--label", required=True)
    box_parser.add_argument("--bbox", required=True, nargs=4, type=float, metavar=("X", "Y", "WIDTH", "HEIGHT"))

    polygon_parser = subparsers.add_parser("create-polygon", help="Create or replace a polygon annotation")
    polygon_parser.add_argument("--project-dir", required=True, type=Path)
    polygon_parser.add_argument("--video-id", required=True)
    polygon_parser.add_argument("--frame-index", required=True, type=int)
    polygon_parser.add_argument("--label", required=True)
    polygon_parser.add_argument(
        "--points",
        required=True,
        help='Polygon vertices as JSON, for example: "[[10,20],[30,20],[30,40]]"',
    )

    assign_parser = subparsers.add_parser("assign-class", help="Assign a class to an existing annotation")
    assign_parser.add_argument("--project-dir", required=True, type=Path)
    assign_parser.add_argument("--annotation-id", required=True)
    assign_parser.add_argument("--class-id", required=True, type=int)
    assign_parser.add_argument("--class-name", required=True)
    assign_parser.add_argument(
        "--taxonomy-path",
        type=Path,
        help="Optional taxonomy JSON path. Defaults to taxonomy.json in the project directory when present.",
    )

    review_parser = subparsers.add_parser("review-frame", help="Mark a frame reviewed or unreviewed")
    review_parser.add_argument("--project-dir", required=True, type=Path)
    review_parser.add_argument("--video-id", required=True)
    review_parser.add_argument("--frame-index", required=True, type=int)
    review_parser.add_argument(
        "--status",
        choices=("reviewed", "unreviewed"),
        required=True,
        help="Frame review status to persist",
    )

    export_parser = subparsers.add_parser(
        "export-navigation-review",
        help="Export deterministic navigation and frame review JSON",
    )
    export_parser.add_argument("--project-dir", required=True, type=Path)
    export_parser.add_argument(
        "--output-path",
        type=Path,
        help="Destination JSON path. Defaults to navigation_review_export.json in the project directory.",
    )

    check_parser = subparsers.add_parser(
        "check-symbols",
        help="Check documented TSR modules and public symbols",
    )
    check_parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Module import path to check; may be repeated. Defaults to documented public modules.",
    )
    check_parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Public symbol as MODULE:SYMBOL; may be repeated. Defaults to documented public symbols.",
    )

    launch_check_parser = subparsers.add_parser(
        "launch-check",
        help="Check TSR launch readiness and return a pass/fail JSON report",
    )
    launch_check_parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Module import path to check; may be repeated. Defaults to documented public modules.",
    )
    launch_check_parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Public symbol as MODULE:SYMBOL; may be repeated. Defaults to documented public symbols.",
    )
    launch_check_parser.add_argument(
        "--report-path",
        type=Path,
        help="Write the launch readiness JSON report to this path for external verification.",
    )
    launch_check_parser.add_argument(
        "--quit-timeout-seconds",
        type=float,
        default=2.0,
        help="Maximum seconds allowed for the quit-path launch check.",
    )

    headless_parser = subparsers.add_parser(
        "headless-simulate",
        help="Run deterministic headless annotation input ticks",
    )
    headless_parser.add_argument("--ticks", required=True, type=int, help="Number of input ticks to execute.")
    headless_parser.add_argument("--total-frames", default=1001, type=int, help="Total frame count to simulate.")
    headless_parser.add_argument("--start-frame", default=0, type=int, help="Initial frame index.")
    headless_parser.add_argument(
        "--include-ticks",
        action="store_true",
        help="Include each tick record in the JSON output for contract tests.",
    )
    headless_parser.add_argument(
        "--trace-path",
        type=Path,
        help="Write one structured JSONL trace entry per executed tick to this path.",
    )

    metadata_parser = subparsers.add_parser(
        "metadata-check",
        help="Load dataset metadata and return a structured pass/fail JSON report",
    )
    metadata_parser.add_argument("--dataset-dir", required=True, type=Path)
    metadata_parser.add_argument(
        "--threshold-seconds",
        type=float,
        default=5.0,
        help="Maximum allowed metadata load duration.",
    )
    metadata_parser.add_argument(
        "--report-path",
        type=Path,
        help="Write the metadata loading JSON report to this path for external verification.",
    )

    loop_parser = subparsers.add_parser(
        "run-loop",
        help="Run the stream-driven annotation loop until a quit signal is received",
    )
    loop_parser.add_argument(
        "--command",
        action="append",
        dest="commands",
        help="Command to inject into the loop; may be repeated. Defaults to reading stdin.",
    )

    benchmark_parser = subparsers.add_parser(
        "benchmark-frame-transitions",
        help="Benchmark adjacent transitions for a controlled JSON frame sequence",
    )
    benchmark_parser.add_argument(
        "--frame-sequence",
        required=True,
        help='JSON array of frame records or IDs, for example: "[0,1,2]"',
    )

    args = parser.parse_args(argv)

    if args.command == "create-box":
        result = create_box_annotation(
            args.project_dir,
            video_id=args.video_id,
            frame_index=args.frame_index,
            label=args.label,
            bbox=tuple(args.bbox),
        )
        _emit_json(result)
        return 0

    if args.command == "create-polygon":
        result = create_polygon_annotation(
            args.project_dir,
            video_id=args.video_id,
            frame_index=args.frame_index,
            label=args.label,
            points=_parse_points(args.points),
        )
        _emit_json(result)
        return 0

    if args.command == "assign-class":
        try:
            result = assign_annotation_class(
                args.project_dir,
                annotation_id=args.annotation_id,
                class_id=args.class_id,
                class_name=args.class_name,
                taxonomy_path=args.taxonomy_path,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        _emit_json(result)
        return 0

    if args.command == "review-frame":
        result = handle_frame_review_command(
            args.project_dir,
            args.status,
            video_id=args.video_id,
            frame_index=args.frame_index,
        )
        _emit_json(result)
        return 0

    if args.command == "export-navigation-review":
        result = export_navigation_review_artifact(args.project_dir, output_path=args.output_path)
        _emit_json(result)
        return 0

    if args.command == "check-symbols":
        result = run_public_contract_check(modules=args.modules, symbols=args.symbols)
        _emit_json(result)
        return 0 if result["ok"] else 1

    if args.command == "launch-check":
        result = run_launch_check(
            modules=args.modules,
            symbols=args.symbols,
            report_path=args.report_path,
            quit_timeout_seconds=args.quit_timeout_seconds,
        )
        _emit_json(result)
        return 0 if result["ok"] else 1

    if args.command == "headless-simulate":
        result = run_headless_simulation(
            tick_count=args.ticks,
            total_frames=args.total_frames,
            start_frame=args.start_frame,
            include_ticks=args.include_ticks,
            trace_path=args.trace_path,
        )
        _emit_json(result)
        return 0 if result["ok"] else 1

    if args.command == "metadata-check":
        result = run_metadata_loading_check(
            args.dataset_dir,
            threshold_seconds=args.threshold_seconds,
            report_path=args.report_path,
        )
        _emit_json(result)
        return 0 if result["ok"] else 1

    if args.command == "run-loop":
        command_source = args.commands if args.commands is not None else sys.stdin
        result = run_annotation_main_loop(command_source)
        _emit_json(result)
        return 0 if result["ok"] else 1

    if args.command == "benchmark-frame-transitions":
        result = handle_frame_transition_benchmark_command(args.frame_sequence)
        _emit_json(result)
        return 0 if result["ok"] else 1

    parser.error(f"unsupported command: {args.command}")
    return 2


def _parse_points(raw_points: str) -> list[list[float]]:
    points = json.loads(raw_points)
    if not isinstance(points, list):
        raise argparse.ArgumentTypeError("points must be a JSON array of [x, y] vertices")
    return points


def _emit_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    raise SystemExit(main())
