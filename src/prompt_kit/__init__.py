"""File-based, deterministic prompt composition for agent harnesses.

Example:
    from prompt_kit import PromptSession, Registry, ToolExecutor

    registry = Registry.load(Path("prompts"))
    session = PromptSession(registry, persona="assistant", config={"agent_name": "Ava"})
    session.activate("default")
    system_prompt = session.system_prompt()
"""

from prompt_kit.loader import PromptLoadError, PromptUnit, Registry
from prompt_kit.models import ErrorKind
from prompt_kit.render import (
    MissingVariableError,
    format_user_data,
    render_fixed_message,
)
from prompt_kit.runtime import (
    ToolCall,
    ToolError,
    ToolExecutor,
    ToolOutcome,
    ToolResolution,
    call_tool_with_retry,
    make_idempotency_key,
)
from prompt_kit.session import PromptSession
from prompt_kit.validate import validate

__all__ = [
    "ErrorKind",
    "MissingVariableError",
    "PromptLoadError",
    "PromptSession",
    "PromptUnit",
    "Registry",
    "ToolCall",
    "ToolError",
    "ToolExecutor",
    "ToolOutcome",
    "ToolResolution",
    "call_tool_with_retry",
    "format_user_data",
    "make_idempotency_key",
    "render_fixed_message",
    "validate",
]
