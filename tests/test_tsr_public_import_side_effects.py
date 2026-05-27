from __future__ import annotations

import builtins
import importlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


PUBLIC_MODULE_PATHS = (
    "tsr_video_annotation_tool",
    "tsr_video_annotation_tool.annotations",
    "tsr_video_annotation_tool.benchmark",
    "tsr_video_annotation_tool.cli",
    "tsr_video_annotation_tool.headless",
    "tsr_video_annotation_tool.launch_check",
    "tsr_video_annotation_tool.metadata",
)


@dataclass(frozen=True)
class PublicSymbol:
    module_path: str
    name: str
    expected_name: str | None = None


DOCUMENTED_PUBLIC_SYMBOLS = (
    PublicSymbol("tsr_video_annotation_tool", "BoxAnnotation"),
    PublicSymbol("tsr_video_annotation_tool", "DatasetMetadata"),
    PublicSymbol("tsr_video_annotation_tool", "FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA"),
    PublicSymbol("tsr_video_annotation_tool", "FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION"),
    PublicSymbol("tsr_video_annotation_tool", "FrameReviewStatus"),
    PublicSymbol("tsr_video_annotation_tool", "FrameTransitionLatencySample"),
    PublicSymbol("tsr_video_annotation_tool", "HeadlessInputTick"),
    PublicSymbol("tsr_video_annotation_tool", "PolygonAnnotation"),
    PublicSymbol("tsr_video_annotation_tool", "aggregate_frame_transition_latency"),
    PublicSymbol("tsr_video_annotation_tool", "assign_annotation_class"),
    PublicSymbol("tsr_video_annotation_tool", "create_box_annotation"),
    PublicSymbol("tsr_video_annotation_tool", "create_polygon_annotation"),
    PublicSymbol("tsr_video_annotation_tool", "export_navigation_review_artifact"),
    PublicSymbol("tsr_video_annotation_tool", "handle_frame_review_command"),
    PublicSymbol("tsr_video_annotation_tool", "handle_frame_transition_benchmark_command"),
    PublicSymbol("tsr_video_annotation_tool", "iter_box_annotations"),
    PublicSymbol("tsr_video_annotation_tool", "iter_frame_review_statuses"),
    PublicSymbol("tsr_video_annotation_tool", "iter_headless_simulation_ticks"),
    PublicSymbol("tsr_video_annotation_tool", "iter_polygon_annotations"),
    PublicSymbol("tsr_video_annotation_tool", "load_box_annotation"),
    PublicSymbol("tsr_video_annotation_tool", "load_dataset_metadata"),
    PublicSymbol("tsr_video_annotation_tool", "load_frame_review_status"),
    PublicSymbol("tsr_video_annotation_tool", "load_polygon_annotation"),
    PublicSymbol("tsr_video_annotation_tool", "run_frame_transition_benchmark"),
    PublicSymbol("tsr_video_annotation_tool", "run_headless_simulation"),
    PublicSymbol("tsr_video_annotation_tool", "run_launch_check"),
    PublicSymbol("tsr_video_annotation_tool", "run_metadata_loading_check"),
    PublicSymbol("tsr_video_annotation_tool", "run_public_contract_check"),
    PublicSymbol("tsr_video_annotation_tool", "set_frame_review_status"),
    PublicSymbol("tsr_video_annotation_tool", "validate_frame_transition_benchmark_response"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "BoxAnnotation"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "FrameReviewStatus"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "PolygonAnnotation"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "assign_annotation_class"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "create_box_annotation"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "create_polygon_annotation"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "export_navigation_review_artifact"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "handle_frame_review_command"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "iter_box_annotations"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "iter_frame_review_statuses"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "iter_polygon_annotations"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "load_box_annotation"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "load_frame_review_status"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "load_polygon_annotation"),
    PublicSymbol("tsr_video_annotation_tool.annotations", "set_frame_review_status"),
    PublicSymbol("tsr_video_annotation_tool.benchmark", "FRAME_TRANSITION_BENCHMARK_SCHEMA_VERSION"),
    PublicSymbol("tsr_video_annotation_tool.benchmark", "FRAME_TRANSITION_BENCHMARK_RESPONSE_SCHEMA"),
    PublicSymbol("tsr_video_annotation_tool.benchmark", "FrameTransitionLatencySample"),
    PublicSymbol("tsr_video_annotation_tool.benchmark", "aggregate_frame_transition_latency"),
    PublicSymbol("tsr_video_annotation_tool.benchmark", "handle_frame_transition_benchmark_command"),
    PublicSymbol("tsr_video_annotation_tool.benchmark", "run_frame_transition_benchmark"),
    PublicSymbol("tsr_video_annotation_tool.benchmark", "validate_frame_transition_benchmark_response"),
    PublicSymbol("tsr_video_annotation_tool.cli", "main"),
    PublicSymbol("tsr_video_annotation_tool.headless", "HeadlessInputTick"),
    PublicSymbol("tsr_video_annotation_tool.headless", "iter_headless_simulation_ticks"),
    PublicSymbol("tsr_video_annotation_tool.headless", "run_headless_simulation"),
    PublicSymbol("tsr_video_annotation_tool.launch_check", "main"),
    PublicSymbol("tsr_video_annotation_tool.launch_check", "run_launch_check"),
    PublicSymbol("tsr_video_annotation_tool.metadata", "DatasetMetadata"),
    PublicSymbol("tsr_video_annotation_tool.metadata", "load_dataset_metadata"),
    PublicSymbol("tsr_video_annotation_tool.metadata", "run_metadata_loading_check"),
)


def test_documented_public_symbols_import_from_documented_module_paths():
    """Every documented TSR public symbol is importable from its documented path."""

    for public_symbol in DOCUMENTED_PUBLIC_SYMBOLS:
        module = importlib.import_module(public_symbol.module_path)
        imported = getattr(module, public_symbol.name)

        assert imported is not None
        assert public_symbol.name in vars(module)
        assert getattr(imported, "__name__", public_symbol.name) == (
            public_symbol.expected_name or public_symbol.name
        )


def test_root_public_api_exports_are_documented_import_symbols():
    """The package-level import contract must stay aligned with __all__."""

    package = importlib.import_module("tsr_video_annotation_tool")
    documented_root_names = {
        public_symbol.name
        for public_symbol in DOCUMENTED_PUBLIC_SYMBOLS
        if public_symbol.module_path == "tsr_video_annotation_tool"
    }

    assert set(package.__all__) == documented_root_names


def test_public_module_imports_do_not_start_runtime_or_write(monkeypatch):
    """Importing documented APIs must be free of runtime, process, and write side effects."""

    blocked_calls: list[str] = []
    original_builtins_open = builtins.open
    original_io_open = io.open
    original_path_open = pathlib.Path.open

    def fail(name: str) -> Callable[..., Any]:
        def _blocked(*args: Any, **kwargs: Any) -> Any:
            blocked_calls.append(name)
            raise AssertionError(f"{name} must not be called during public module import")

        return _blocked

    def blocks_writes(mode: Any) -> bool:
        if mode is None:
            return False
        return any(flag in str(mode) for flag in ("w", "a", "x", "+"))

    def guarded_builtin_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if blocks_writes(mode):
            return fail("builtins.open(write)")()
        return original_builtins_open(file, mode, *args, **kwargs)

    def guarded_io_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if blocks_writes(mode):
            return fail("io.open(write)")()
        return original_io_open(file, mode, *args, **kwargs)

    def guarded_path_open(
        self: pathlib.Path,
        mode: str = "r",
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if blocks_writes(mode):
            return fail("pathlib.Path.open(write)")()
        return original_path_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_builtin_open)
    monkeypatch.setattr(io, "open", guarded_io_open)
    monkeypatch.setattr(pathlib.Path, "open", guarded_path_open)
    monkeypatch.setattr(os, "open", fail("os.open"))
    monkeypatch.setattr(os, "replace", fail("os.replace"))
    monkeypatch.setattr(tempfile, "mkstemp", fail("tempfile.mkstemp"))

    for process_api in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, process_api, fail(f"subprocess.{process_api}"))
    monkeypatch.setattr(os, "system", fail("os.system"))
    monkeypatch.setattr(os, "spawnv", fail("os.spawnv"))
    monkeypatch.setattr(os, "spawnve", fail("os.spawnve"))

    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        for module_path in PUBLIC_MODULE_PATHS:
            sys.modules.pop(module_path, None)
        for module_path in PUBLIC_MODULE_PATHS:
            importlib.import_module(module_path)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode

    assert blocked_calls == []
