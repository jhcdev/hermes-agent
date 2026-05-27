from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_PUBLIC_MODULES = (
    "tsr_video_annotation_tool",
    "tsr_video_annotation_tool.annotations",
    "tsr_video_annotation_tool.benchmark",
    "tsr_video_annotation_tool.cli",
    "tsr_video_annotation_tool.headless",
    "tsr_video_annotation_tool.launch_check",
    "tsr_video_annotation_tool.metadata",
)

DEFAULT_PUBLIC_SYMBOLS = (
    "tsr_video_annotation_tool:BoxAnnotation",
    "tsr_video_annotation_tool:DatasetMetadata",
    "tsr_video_annotation_tool:FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA",
    "tsr_video_annotation_tool:FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION",
    "tsr_video_annotation_tool:PolygonAnnotation",
    "tsr_video_annotation_tool:FrameReviewStatus",
    "tsr_video_annotation_tool:FrameTransitionLatencySample",
    "tsr_video_annotation_tool:HeadlessInputTick",
    "tsr_video_annotation_tool:assign_annotation_class",
    "tsr_video_annotation_tool:create_box_annotation",
    "tsr_video_annotation_tool:create_polygon_annotation",
    "tsr_video_annotation_tool:export_navigation_review_artifact",
    "tsr_video_annotation_tool:handle_frame_review_command",
    "tsr_video_annotation_tool:handle_frame_transition_benchmark_command",
    "tsr_video_annotation_tool:iter_box_annotations",
    "tsr_video_annotation_tool:iter_headless_simulation_ticks",
    "tsr_video_annotation_tool:iter_polygon_annotations",
    "tsr_video_annotation_tool:iter_frame_review_statuses",
    "tsr_video_annotation_tool:load_box_annotation",
    "tsr_video_annotation_tool:load_dataset_metadata",
    "tsr_video_annotation_tool:load_polygon_annotation",
    "tsr_video_annotation_tool:load_frame_review_status",
    "tsr_video_annotation_tool:run_frame_transition_benchmark",
    "tsr_video_annotation_tool:run_headless_simulation",
    "tsr_video_annotation_tool:run_launch_check",
    "tsr_video_annotation_tool:run_metadata_loading_check",
    "tsr_video_annotation_tool:run_public_contract_check",
    "tsr_video_annotation_tool:set_frame_review_status",
    "tsr_video_annotation_tool:validate_frame_transition_benchmark_response",
    "tsr_video_annotation_tool.annotations:BoxAnnotation",
    "tsr_video_annotation_tool.annotations:PolygonAnnotation",
    "tsr_video_annotation_tool.annotations:FrameReviewStatus",
    "tsr_video_annotation_tool.annotations:assign_annotation_class",
    "tsr_video_annotation_tool.annotations:create_box_annotation",
    "tsr_video_annotation_tool.annotations:create_polygon_annotation",
    "tsr_video_annotation_tool.annotations:export_navigation_review_artifact",
    "tsr_video_annotation_tool.annotations:handle_frame_review_command",
    "tsr_video_annotation_tool.annotations:iter_box_annotations",
    "tsr_video_annotation_tool.annotations:iter_polygon_annotations",
    "tsr_video_annotation_tool.annotations:iter_frame_review_statuses",
    "tsr_video_annotation_tool.annotations:load_box_annotation",
    "tsr_video_annotation_tool.annotations:load_polygon_annotation",
    "tsr_video_annotation_tool.annotations:load_frame_review_status",
    "tsr_video_annotation_tool.annotations:set_frame_review_status",
    "tsr_video_annotation_tool.benchmark:FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION",
    "tsr_video_annotation_tool.benchmark:FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA",
    "tsr_video_annotation_tool.benchmark:FrameTransitionLatencySample",
    "tsr_video_annotation_tool.benchmark:aggregate_frame_transition_latency",
    "tsr_video_annotation_tool.benchmark:handle_frame_transition_benchmark_command",
    "tsr_video_annotation_tool.benchmark:run_frame_transition_benchmark",
    "tsr_video_annotation_tool.benchmark:validate_frame_transition_benchmark_response",
    "tsr_video_annotation_tool.cli:main",
    "tsr_video_annotation_tool.headless:HeadlessInputTick",
    "tsr_video_annotation_tool.headless:iter_headless_simulation_ticks",
    "tsr_video_annotation_tool.headless:run_headless_simulation",
    "tsr_video_annotation_tool.launch_check:main",
    "tsr_video_annotation_tool.launch_check:run_launch_check",
    "tsr_video_annotation_tool.metadata:DatasetMetadata",
    "tsr_video_annotation_tool.metadata:load_dataset_metadata",
    "tsr_video_annotation_tool.metadata:run_metadata_loading_check",
)

PUBLIC_CONTRACT_SCHEMA_VERSION = "tsr-public-contract-check-v1"


@dataclass(frozen=True)
class ModuleCheck:
    module: str
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class SymbolCheck:
    module: str
    symbol: str
    ok: bool
    error: str | None = None


def run_public_contract_check(
    *,
    modules: tuple[str, ...] | list[str] | None = None,
    symbols: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Import configured modules/symbols and return a JSON-serializable report."""

    module_names = tuple(modules or DEFAULT_PUBLIC_MODULES)
    symbol_specs = tuple(symbols or DEFAULT_PUBLIC_SYMBOLS)

    module_results = [_check_module(module_name) for module_name in module_names]
    symbol_results = [_check_symbol(symbol_spec) for symbol_spec in symbol_specs]
    ok = all(result.ok for result in module_results) and all(result.ok for result in symbol_results)

    return {
        "ok": ok,
        "schema_version": PUBLIC_CONTRACT_SCHEMA_VERSION,
        "summary": {
            "modules_checked": len(module_results),
            "modules_failed": sum(not result.ok for result in module_results),
            "symbols_checked": len(symbol_results),
            "symbols_failed": sum(not result.ok for result in symbol_results),
        },
        "modules": [asdict(result) for result in module_results],
        "symbols": [asdict(result) for result in symbol_results],
    }


def _check_module(module_name: str) -> ModuleCheck:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        return ModuleCheck(module=module_name, ok=False, error=f"{type(exc).__name__}: {exc}")
    return ModuleCheck(module=module_name, ok=True)


def _check_symbol(symbol_spec: str) -> SymbolCheck:
    if ":" not in symbol_spec:
        return SymbolCheck(module="", symbol=symbol_spec, ok=False, error="symbol spec must be MODULE:SYMBOL")

    module_name, symbol_name = symbol_spec.split(":", 1)
    if not module_name or not symbol_name:
        return SymbolCheck(module=module_name, symbol=symbol_name, ok=False, error="module and symbol are required")

    try:
        module = importlib.import_module(module_name)
        getattr(module, symbol_name)
    except Exception as exc:
        return SymbolCheck(module=module_name, symbol=symbol_name, ok=False, error=f"{type(exc).__name__}: {exc}")
    return SymbolCheck(module=module_name, symbol=symbol_name, ok=True)
