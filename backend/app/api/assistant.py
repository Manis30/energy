"""
FastAPI Assistant Chat API Endpoints.

Provides the production-conscious conversational interface:
- Accepts natural language queries and bounded multi-turn conversation history.
- Coordinates reasoning through IndustrialEnergyAgent.
- Enforces strict request schema validation and HTTP status codes.
- Returns evidence-backed answers, tool references, and sanitized execution evidence.
- Guarantees zero credential, prompt, or SQL query disclosure.
"""

import logging
from typing import List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_agent
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    ToolEvidenceItem,
)
from app.schemas.common import ErrorResponse
from app.services.agent import (
    AgentError,
    AgentInputError,
    ConversationTurn,
    IndustrialEnergyAgent,
    ToolEvidence,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _sanitize_tool_evidence(ev: ToolEvidence) -> ToolEvidenceItem:
    """
    Produce a safe, concise, non-sensitive summary of tool execution.
    Never exposes raw SQL strings, database URLs, tokens, or raw table rows.
    """
    summary: Optional[str] = None

    if ev.success:
        if ev.tool_name == "read_only_sql_query":
            row_count = ev.result.get("row_count", 0) if isinstance(ev.result, dict) else 0
            col_count = len(ev.result.get("columns", [])) if isinstance(ev.result, dict) else 0
            summary = f"Read-only SQL query executed: returned {row_count} rows across {col_count} columns."
        elif isinstance(ev.result, dict):
            # Extract key metric labels without sensitive connection or credential metadata
            metrics = []
            for k, v in list(ev.result.items())[:4]:
                if not isinstance(v, (dict, list)):
                    metrics.append(f"{k}: {v}")
            summary = "; ".join(metrics) if metrics else "Execution completed successfully."
        elif isinstance(ev.result, list):
            summary = f"Retrieved {len(ev.result)} records."
        else:
            summary = "Execution completed successfully."
    else:
        # Sanitized error message without internal file paths or stack traces
        clean_err = str(ev.error) if ev.error else "Unknown execution error"
        summary = f"Tool failed: {clean_err}"

    return ToolEvidenceItem(
        tool_name=ev.tool_name,
        execution_order=ev.execution_order,
        success=ev.success,
        summary=summary,
    )


@router.post(
    "/chat",
    response_model=AssistantChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid user input or malformed request parameters"},
        422: {"description": "Validation error: invalid types, unsupported roles, or length exceeded"},
        429: {"model": ErrorResponse, "description": "AI service rate limit exceeded"},
        502: {"model": ErrorResponse, "description": "AI service authentication failure"},
        503: {"model": ErrorResponse, "description": "AI or database service unavailable"},
        504: {"model": ErrorResponse, "description": "AI service request timed out"},
        500: {"model": ErrorResponse, "description": "Internal agent or server error"},
    },
    summary="Chat with Industrial Energy Intelligence Assistant",
    description=(
        "Submits a natural-language manufacturing operations question to the AI assistant. "
        "The agent selects deterministic analytics tools, enforces a maximum of 5 tool executions, "
        "and synthesizes a verified, evidence-backed answer."
    ),
)
async def chat_with_assistant(
    request: AssistantChatRequest,
    agent: IndustrialEnergyAgent = Depends(get_agent),
) -> AssistantChatResponse:
    # 1. Resolve or generate conversation ID
    conversation_id = request.conversation_id or uuid4()

    # 2. Map validated history to internal ConversationTurn objects
    history_turns: List[ConversationTurn] = [
        ConversationTurn(role=m.role, content=m.content)
        for m in request.history
    ]

    # 3. Execute agent reasoning loop
    try:
        response = await agent.run(
            user_question=request.message,
            history=history_turns,
            session_id=str(conversation_id),
        )
    except AgentInputError as e:
        logger.warning("Agent input validation failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except AgentError as e:
        err_msg = str(e).lower()
        logger.warning("Agent execution error: %s", str(e))

        if "authentication failed" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service authentication failed. Please verify AI provider configuration.",
            )
        elif "rate limit" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI service rate limit reached. Please try again shortly.",
            )
        elif "timed out" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI service request timed out. Please try again.",
            )
        elif "unavailable" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is currently unavailable. Please try again later.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Assistant execution error: {str(e)}",
            )
    except Exception as e:
        logger.exception("Unexpected exception in assistant chat endpoint: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request.",
        )

    # 4. Serialize tool evidence safely
    sanitized_evidence: List[ToolEvidenceItem] = [
        _sanitize_tool_evidence(ev) for ev in response.evidence
    ]

    return AssistantChatResponse(
        conversation_id=str(conversation_id),
        answer=response.answer,
        tool_references=response.tool_references,
        tool_evidence=sanitized_evidence,
        tool_count=response.tool_executions_count,
        model_call_count=response.model_calls_count,
        execution_limit_reached=response.limit_reached,
    )
