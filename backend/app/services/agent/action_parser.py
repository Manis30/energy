"""
Strict JSON Action Parser and Validator for Industrial Energy Intelligence Agent.

Enforces the controlled JSON-action protocol:
- Every action must be valid JSON conforming to either 'tool_call' or 'final' schema.
- Rejects unexpected/extraneous fields.
- Verifies tool names against the 21 registered deterministic tools.
- Validates tool arguments against corresponding Pydantic tool schemas without silent mutation.
- Distinguishes syntax errors, unknown tools, and invalid arguments with specific error types.
"""

import json
import re
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from langchain_core.exceptions import OutputParserException
from app.services.agent.tool_registry import TOOL_REGISTRY, get_tool


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AgentActionError(OutputParserException):
    """Base exception for action parsing and validation failures."""
    pass


class ActionParseError(AgentActionError):
    """Raised when the raw model output cannot be parsed as valid action JSON or has unexpected structure."""
    pass


class ToolNotFoundError(AgentActionError):
    """Raised when the model requests a tool name that is not registered."""
    pass


class ToolArgumentError(AgentActionError):
    """Raised when tool arguments fail Pydantic schema validation."""
    pass


# ---------------------------------------------------------------------------
# Action Schemas
# ---------------------------------------------------------------------------

class ToolCallAction(BaseModel):
    """Structured tool execution request from the model."""
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call"]
    tool_name: str = Field(..., min_length=1, description="Exact registered tool identifier")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool invocation parameters")
    reason: Optional[str] = Field(default=None, description="Technical rationale for invoking this tool")


class FinalAnswerAction(BaseModel):
    """Structured final response from the model to the user."""
    model_config = ConfigDict(extra="forbid")

    type: Literal["final"]
    answer: str = Field(..., min_length=1, description="Comprehensive, evidence-backed answer")
    tool_references: List[str] = Field(default_factory=list, description="Registered tools providing evidence")


AgentAction = Union[ToolCallAction, FinalAnswerAction]


# ---------------------------------------------------------------------------
# Parsing & Validation Functions
# ---------------------------------------------------------------------------

def _extract_json_string(raw_text: str) -> str:
    """
    Extract JSON string from model response, handling pure JSON or markdown code fences.
    Rejects text that mixes prose with JSON.
    """
    if not raw_text or not raw_text.strip():
        raise ActionParseError("Model output is empty. A valid JSON action object is required.")

    text = raw_text.strip()

    # If wrapped in markdown code fence (```json ... ``` or ``` ... ```)
    fence_pattern = r"^```(?:json)?\s*\n?([\s\S]*?)\n?```$"
    fence_match = re.match(fence_pattern, text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    # Ensure no leading/trailing conversational text outside the JSON object
    if not (text.startswith("{") and text.endswith("}")):
        # If there is prose surrounding JSON or no JSON object at all
        raise ActionParseError(
            "Model response must be a single raw JSON object without conversational prose outside the object."
        )

    return text


def parse_agent_action(raw_text: str) -> AgentAction:
    """
    Strictly parse and validate a model response into a typed AgentAction.

    Steps:
    1. Parse JSON strictly.
    2. Enforce root structure is a dictionary.
    3. Validate action 'type' is either 'tool_call' or 'final'.
    4. For 'tool_call':
       - Enforce no unexpected fields.
       - Validate tool_name against TOOL_REGISTRY.
       - Validate arguments against the tool's Pydantic args_schema without silent alteration.
    5. For 'final':
       - Enforce no unexpected fields.
       - Validate answer is non-empty string.
       - Validate tool_references is a list of strings.

    Returns:
        Validated ToolCallAction or FinalAnswerAction.

    Raises:
        ActionParseError: On malformed JSON, invalid root type, unexpected fields, or missing core fields.
        ToolNotFoundError: If requested tool is not in the registry.
        ToolArgumentError: If arguments violate the tool's Pydantic schema.
    """
    json_str = _extract_json_string(raw_text)

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ActionParseError(f"Malformed JSON: {e.msg} at line {e.lineno} column {e.colno}.") from e

    if not isinstance(parsed, dict):
        raise ActionParseError(
            f"Expected JSON root to be an object (dict), but received {type(parsed).__name__}."
        )

    action_type = parsed.get("type")
    if action_type is None:
        raise ActionParseError("Missing required 'type' field in JSON action. Must be 'tool_call' or 'final'.")

    if action_type == "tool_call":
        # 1. Parse ToolCallAction (validates structure and rejects unexpected fields)
        try:
            action = ToolCallAction.model_validate(parsed)
        except ValidationError as e:
            err_details = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            raise ActionParseError(f"Invalid tool_call action structure: {err_details}") from e

        # 2. Validate tool_name exists in registry
        tool = get_tool(action.tool_name)
        if tool is None:
            available = sorted(list(TOOL_REGISTRY.keys()))
            raise ToolNotFoundError(
                f"Tool '{action.tool_name}' is not registered. Available tools: {available}"
            )

        # 3. Validate arguments against tool's Pydantic schema
        if not isinstance(action.arguments, dict):
            raise ToolArgumentError(
                f"Arguments for tool '{action.tool_name}' must be a dictionary, got {type(action.arguments).__name__}."
            )

        if tool.args_schema:
            try:
                # Strictly validate arguments using tool's Pydantic schema
                # We model_validate to verify required fields, types, and custom validators
                # (e.g. start_date > end_date, z_threshold bounds, etc.)
                tool.args_schema.model_validate(action.arguments)
            except ValidationError as e:
                err_messages = []
                for err in e.errors():
                    field_name = ".".join(str(loc) for loc in err["loc"]) if err["loc"] else "root"
                    err_messages.append(f"{field_name}: {err['msg']}")
                raise ToolArgumentError(
                    f"Invalid arguments for tool '{action.tool_name}': {'; '.join(err_messages)}"
                ) from e

        return action

    elif action_type == "final":
        # 1. Parse FinalAnswerAction (validates structure and rejects unexpected fields)
        try:
            action = FinalAnswerAction.model_validate(parsed)
        except ValidationError as e:
            err_details = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            raise ActionParseError(f"Invalid final action structure: {err_details}") from e

        # Ensure answer is non-empty after stripping
        if not action.answer.strip():
            raise ActionParseError("Final answer cannot be empty or whitespace only.")

        # Ensure tool_references contains only strings
        if not isinstance(action.tool_references, list) or not all(isinstance(r, str) for r in action.tool_references):
            raise ActionParseError("tool_references must be a list of string tool names.")

        return action

    else:
        raise ActionParseError(
            f"Unknown action type '{action_type}'. Only 'tool_call' and 'final' are permitted."
        )
