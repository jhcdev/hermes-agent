from __future__ import annotations

from types import SimpleNamespace

from agent.agent_runtime_helpers import refresh_reasoning_content_for_active_provider


class _Agent(SimpleNamespace):
    def __init__(self, needs_pad: bool):
        super().__init__(_needs=needs_pad)

    def _needs_thinking_reasoning_pad(self) -> bool:
        return self._needs


def test_refresh_adds_reasoning_content_after_fallback_runtime_switch():
    """Fallback retries rebuild provider-sensitive reasoning echo fields.

    The original API copy may have been built for a primary provider that does
    not require reasoning_content.  If the retry loop switches in-place to
    DeepSeek/Kimi/MiMo, the same history must be refreshed before replay.
    """
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "run a tool"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "terminal", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ]

    refresh_reasoning_content_for_active_provider(_Agent(needs_pad=True), messages)

    assistant_messages = [m for m in messages if m["role"] == "assistant"]
    assert assistant_messages
    assert all(m.get("reasoning_content") == " " for m in assistant_messages)


def test_refresh_upgrades_empty_string_placeholder_for_thinking_provider():
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [], "reasoning_content": ""},
    ]

    refresh_reasoning_content_for_active_provider(_Agent(needs_pad=True), messages)

    assert messages[0]["reasoning_content"] == " "


def test_refresh_does_not_add_reasoning_content_when_provider_does_not_need_pad():
    messages = [{"role": "assistant", "content": "done"}]

    refresh_reasoning_content_for_active_provider(_Agent(needs_pad=False), messages)

    assert "reasoning_content" not in messages[0]
