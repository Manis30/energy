"""
Assistant API Request and Response Schemas.

Defines validated data models for the AI Assistant chat endpoint:
- Strictly validates user messages (trimmed, non-empty, max 2000 chars).
- Validates conversation IDs as standard UUIDs.
- Restricts conversation history to max 10 turns with only 'user' and 'assistant' roles.
- Exposes structured, sanitized tool execution evidence without leaking secrets or raw SQL.
"""

from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessage(BaseModel):
    """A single user or assistant conversational turn in conversation history."""
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"] = Field(
        ...,
        description="Role of the message sender. Strictly 'user' or 'assistant'.",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Text content of the message.",
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Message content cannot be empty or whitespace only.")
        return cleaned


class AssistantChatRequest(BaseModel):
    """Payload sent to POST /api/assistant/chat."""
    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User natural-language query regarding manufacturing operations.",
    )
    conversation_id: Optional[UUID] = Field(
        None,
        description="Optional UUID tracking conversation context. Generated if omitted.",
    )
    history: List[ChatMessage] = Field(
        default_factory=list,
        max_length=10,
        description="Optional prior conversation turns (maximum 10 turns).",
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("User message cannot be empty or whitespace only.")
        return cleaned


class ToolEvidenceItem(BaseModel):
    """Sanitized evidence record of an executed analytical tool."""
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Registered tool identifier")
    execution_order: int = Field(..., description="1-indexed execution order within the turn")
    success: bool = Field(..., description="Whether tool execution completed successfully")
    summary: Optional[str] = Field(
        None,
        description="Concise technical summary of output or sanitized error description",
    )


class ClaimVerificationItem(BaseModel):
    """Detailed verification outcome for an individual numerical claim."""
    model_config = ConfigDict(extra="forbid")

    claimed_number: str = Field(..., description="Exact numerical string parsed from assistant response")
    metric: Optional[str] = Field(None, description="Inferred or matched metric category (energy, cost, production, etc.)")
    unit: Optional[str] = Field(None, description="Metric unit (kWh, INR, %, units, minutes, etc.)")
    scope: Optional[str] = Field(None, description="Applicable plant, meter, line, product, or shift scope")
    outcome: str = Field(..., description="Verification outcome: VERIFIED, UNVERIFIED, CONFLICTING, SCOPE_MISMATCH, UNIT_MISMATCH, or NOT_APPLICABLE")
    authoritative_value: Optional[str] = Field(None, description="Authoritative numeric value from successful backend tool results")
    authoritative_unit: Optional[str] = Field(None, description="Authoritative unit from backend evidence")
    supporting_tool: Optional[str] = Field(None, description="Identifier of the successful tool providing authoritative evidence")
    explanation: str = Field(..., description="Deterministic verification rationale or mismatch diagnosis")
    was_corrected: bool = Field(default=False, description="Whether an unambiguous conflicting claim was corrected in the response")


class AssistantChatResponse(BaseModel):
    """Structured response returned by POST /api/assistant/chat."""
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="UUID string identifying this conversation")
    answer: str = Field(..., description="Comprehensive, evidence-backed answer")
    tool_references: List[str] = Field(
        default_factory=list,
        description="Names of registered tools supporting the numerical claims",
    )
    tool_evidence: List[ToolEvidenceItem] = Field(
        default_factory=list,
        description="Sanitized tool execution evidence records",
    )
    tool_count: int = Field(..., description="Number of tool executions performed in this turn")
    model_call_count: int = Field(..., description="Number of model reasoning calls performed")
    execution_limit_reached: bool = Field(
        default=False,
        description="True if the hard limit of 5 tool executions was reached",
    )
    verification_status: Optional[str] = Field(
        default="VERIFIED",
        description="Overall response verification status: VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, CONFLICT_DETECTED, or NO_ANALYTIC_CLAIMS",
    )
    claims: List[ClaimVerificationItem] = Field(
        default_factory=list,
        description="Deterministic verification outcomes for individual numerical claims in the response",
    )
    verified_claims_count: int = Field(
        default=0,
        description="Count of numerical claims successfully verified against backend evidence",
    )
    unverified_claims_count: int = Field(
        default=0,
        description="Count of numerical claims that could not be verified against backend evidence",
    )
