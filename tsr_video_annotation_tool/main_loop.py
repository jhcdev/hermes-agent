from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, TextIO


MAIN_LOOP_SCHEMA_VERSION = "tsr-main-loop-v1"
QUIT_COMMANDS = frozenset({"quit", "q", "exit"})


@dataclass(frozen=True)
class MainLoopResult:
    """Observable result for the annotation command loop."""

    ok: bool
    schema_version: str
    status: str
    termination_path: str
    quit_signal_received: bool
    processed_commands: int
    ignored_commands: list[str] = field(default_factory=list)

    def to_json_record(self) -> dict[str, object]:
        return asdict(self)


def run_annotation_main_loop(command_source: Iterable[str] | TextIO) -> dict[str, object]:
    """Run the annotation command loop until a normal quit signal is received.

    The loop is intentionally stream-oriented so tests and launch wrappers can
    inject commands without a TTY. Unknown commands are ignored for now because
    GT/Delta actions are handled by dedicated APIs and CLI subcommands.
    """

    processed_commands = 0
    ignored_commands: list[str] = []

    for raw_command in command_source:
        command = raw_command.strip().lower()
        if not command:
            continue

        processed_commands += 1
        if command in QUIT_COMMANDS:
            return MainLoopResult(
                ok=True,
                schema_version=MAIN_LOOP_SCHEMA_VERSION,
                status="terminated",
                termination_path="normal",
                quit_signal_received=True,
                processed_commands=processed_commands,
                ignored_commands=ignored_commands,
            ).to_json_record()

        ignored_commands.append(command)

    return MainLoopResult(
        ok=False,
        schema_version=MAIN_LOOP_SCHEMA_VERSION,
        status="input_exhausted",
        termination_path="abnormal",
        quit_signal_received=False,
        processed_commands=processed_commands,
        ignored_commands=ignored_commands,
    ).to_json_record()
