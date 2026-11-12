"""AI Agent and Tool Foundation for Industrial Energy Intelligence Platform."""

from app.services.agent.action_parser import (
    ActionParseError,
    AgentAction,
    AgentActionError,
    FinalAnswerAction,
    ToolArgumentError,
    ToolCallAction,
    ToolNotFoundError,
    parse_agent_action,
)
from app.services.agent.agent import (
    AgentError,
    AgentInputError,
    AgentResponse,
    IndustrialEnergyAgent,
    MaxModelCallsError,
    MaxToolExecutionsError,
    ToolEvidence,
)
from app.services.agent.conversation import (
    ConversationContext,
    ConversationTurn,
)
from app.services.agent.domo_client import (
    DomoAuthenticationError,
    DomoClient,
    DomoConfigurationError,
    DomoConnectionError,
    DomoError,
    DomoRateLimitError,
    DomoResponseError,
    DomoServerError,
    DomoTextGenerationRequest,
    DomoTextGenerationResponse,
    DomoTimeoutError,
    get_domo_client,
)
from app.services.agent.prompts import (
    build_react_prompt,
    format_tool_catalog,
    get_correction_prompt,
    get_limit_reached_prompt,
    get_system_prompt,
)
from app.services.agent.sql_tool import (
    ReadOnlySQLQueryInput,
    SQLExecutionError,
    execute_read_only_sql,
)
from app.services.agent.sql_validator import (
    SQLValidationError,
    validate_sql,
)
from app.services.agent.tool_registry import (
    TOOL_REGISTRY,
    DeterministicTool,
    execute_tool,
    get_all_tools,
    get_tool,
    get_tool_descriptions,
)

__all__ = [
    # Agent & Orchestration
    "IndustrialEnergyAgent",
    "AgentResponse",
    "ToolEvidence",
    "AgentError",
    "AgentInputError",
    "MaxToolExecutionsError",
    "MaxModelCallsError",
    # Action Parser
    "ActionParseError",
    "ToolNotFoundError",
    "ToolArgumentError",
    "AgentActionError",
    "ToolCallAction",
    "FinalAnswerAction",
    "AgentAction",
    "parse_agent_action",
    # Conversation
    "ConversationContext",
    "ConversationTurn",
    # Prompts
    "get_system_prompt",
    "build_react_prompt",
    "get_correction_prompt",
    "get_limit_reached_prompt",
    "format_tool_catalog",
    # Domo Client
    "DomoClient",
    "DomoError",
    "DomoConfigurationError",
    "DomoAuthenticationError",
    "DomoRateLimitError",
    "DomoServerError",
    "DomoTimeoutError",
    "DomoConnectionError",
    "DomoResponseError",
    "DomoTextGenerationRequest",
    "DomoTextGenerationResponse",
    "get_domo_client",
    # SQL Tool & Validator
    "ReadOnlySQLQueryInput",
    "SQLExecutionError",
    "execute_read_only_sql",
    "SQLValidationError",
    "validate_sql",
    # Tool Registry
    "TOOL_REGISTRY",
    "DeterministicTool",
    "get_all_tools",
    "get_tool",
    "execute_tool",
    "get_tool_descriptions",
]
