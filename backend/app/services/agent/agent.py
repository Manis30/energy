"""
Controlled ReAct AI Agent for Industrial Energy Intelligence Platform.

Coordinates the reasoning and tool execution loop:
1. Validates user input and conversation context.
2. Formulates prompt with domain rules, tool catalog, and ReAct history.
3. Invokes Domo Text Generation API via DomoClient.
4. Strictly parses and validates model action via ActionParser.
5. Strictly enforces a HARD limit of maximum 5 tool calls per user turn.
6. Executes registered deterministic tools or read-only SQL queries with isolated sessions.
7. Tracks internal evidence records for all tool executions.
8. Enforces bounded correction attempts for invalid model output.
9. Ensures final response is backed by actual executed tools without fabrication.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Union

from app.services.agent.action_parser import (
    ActionParseError,
    AgentAction,
    FinalAnswerAction,
    ToolArgumentError,
    ToolCallAction,
    ToolNotFoundError,
    parse_agent_action,
)
from app.services.agent.conversation import ConversationContext, ConversationTurn
from app.services.agent.domo_client import (
    DomoAuthenticationError,
    DomoClient,
    DomoConnectionError,
    DomoError,
    DomoRateLimitError,
    DomoServerError,
    DomoTimeoutError,
    get_domo_client,
)
from app.services.agent.prompts import (
    build_react_prompt,
    get_correction_prompt,
    get_limit_reached_prompt,
    get_system_prompt,
)
from app.services.agent.sql_tool import SQLExecutionError
from app.services.agent.sql_validator import SQLValidationError
from app.services.agent.tool_registry import (
    TOOL_REGISTRY,
    execute_tool,
    get_tool,
)
from app.services.agent.evidence_verifier import (
    ClaimVerificationResult,
    VerificationOutcome,
    VerificationResponse,
    VerificationSummary,
    verify_numeric_claims,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AgentError(Exception):
    """Base exception for agent execution and orchestration failures."""
    pass


class AgentInputError(AgentError):
    """Raised when user input fails basic validation."""
    pass


class MaxToolExecutionsError(AgentError):
    """Raised when maximum allowed tool executions (5) is exceeded."""
    pass


class MaxModelCallsError(AgentError):
    """Raised when maximum allowed model calls is reached without resolution."""
    pass


# ---------------------------------------------------------------------------
# Evidence & Response Models
# ---------------------------------------------------------------------------

@dataclass
class ToolEvidence:
    """Internal record of a tool execution and its deterministic output."""
    execution_order: int
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_order": self.execution_order,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": self.result,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class AgentResponse:
    """Final structured response returned by the agent."""
    answer: str
    tool_references: List[str]
    evidence: List[ToolEvidence]
    tool_executions_count: int
    model_calls_count: int
    limit_reached: bool = False
    verification_status: str = "VERIFIED"
    claims: List[Dict[str, Any]] = field(default_factory=list)
    verified_claims_count: int = 0
    unverified_claims_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "tool_references": self.tool_references,
            "evidence": [e.to_dict() for e in self.evidence],
            "tool_executions_count": self.tool_executions_count,
            "model_calls_count": self.model_calls_count,
            "limit_reached": self.limit_reached,
            "verification_status": self.verification_status,
            "claims": self.claims,
            "verified_claims_count": self.verified_claims_count,
            "unverified_claims_count": self.unverified_claims_count,
        }


# ---------------------------------------------------------------------------
# Serialization Helper
# ---------------------------------------------------------------------------

def _json_serial(val: Any) -> Any:
    """Format row values preserving Decimal precision and ISO dates without inventing timezones."""
    if isinstance(val, Decimal):
        return float(val) if val.is_finite() else str(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    raise TypeError(f"Object of type {type(val).__name__} is not JSON serializable")


def _serialize_tool_output(result: Any) -> str:
    """Serialize tool result dictionary/list to formatted JSON string."""
    try:
        return json.dumps(result, default=_json_serial, indent=2)
    except Exception as e:
        logger.warning("Failed to cleanly JSON serialize tool output: %s", str(e))
        return json.dumps({"raw": str(result)})


def _prepare_tool_output_for_llm(tool_name: str, result: Any) -> Any:
    """
    Prepare a sanitized, size-controlled representation of tool output for LLM prompt context.
    Preserves exact aggregate totals and counts while summarizing large item collections
    (e.g., >5 anomaly records or >10 SQL rows) to prevent prompt bloat or silent truncation.
    Note: Full, unaltered results remain safely stored in ToolEvidence.result.
    """
    if result is None:
        return {"status": "empty", "result": None}

    if not isinstance(result, dict):
        if isinstance(result, list) and len(result) > 10:
            return {
                "total_items": len(result),
                "sample_items": result[:10],
                "note": f"Displaying 10 of {len(result)} items for LLM context. Full records preserved in evidence.",
            }
        return result

    summary = dict(result)

    # 1. Anomaly tools with 'anomalies' list
    if "anomalies" in summary and isinstance(summary["anomalies"], list) and len(summary["anomalies"]) > 5:
        total = len(summary["anomalies"])
        summary["anomalies_sample"] = summary["anomalies"][:5]
        summary["total_anomalies_detected"] = total
        summary["note"] = f"Displaying top 5 sample anomalies out of {total} total records. Complete records preserved in tool evidence."
        del summary["anomalies"]

    # 2. Unified anomaly detection category lists
    for cat in ("statistical_anomalies", "rolling_baseline_anomalies", "low_pf_anomalies", "standby_anomalies"):
        if cat in summary and isinstance(summary[cat], list) and len(summary[cat]) > 5:
            total = len(summary[cat])
            summary[f"{cat}_sample"] = summary[cat][:5]
            summary[f"total_{cat}_detected"] = total
            del summary[cat]

    # 3. SQL query rows
    if "rows" in summary and isinstance(summary["rows"], list) and len(summary["rows"]) > 10:
        total = len(summary["rows"])
        summary["rows_sample"] = summary["rows"][:10]
        summary["total_rows_returned"] = total
        summary["note"] = f"Displaying 10 sample rows out of {total} total rows."
        del summary["rows"]

    return summary


# Analytical and educational query detection patterns
ANALYTICAL_INDICATORS = [
    r'\b(yesterday|today|last week|last month|in \d{4}|\d{4}-\d{2}-\d{2})\b',
    r'\b(plant|line|meter|shift|sku|product)\b',
    r'\b(in-tn-01|smt-l1|smt-l2|fal-l1|fal-l2|mtr-\w+|sph-\w+)\b',
    r'\b(how much|how many|total|average|peak|highest|lowest|sum|cost|kwh|inr|count)\b',
    r'\b(show me|give me|list|find|display|get|fetch|calculate|trend|breakdown)\b',
    r'\b(anomal(?:y|ies)|outlier|spike|downtime|reject|scrap|rework|produced|units|sec|intensity)\b',
]

EDUCATIONAL_PATTERNS = [
    r'^(what is|what are|explain|define|how do you calculate|how is .* calculated|what does .* mean|what does .* stand for)\b',
    r'\b(methodology|definition|formula|concept|difference between)\b',
    r'^(what tools|list tools|help)\b',
]

UNSUPPORTED_DOMAINS = [
    r'\b(oee|overall equipment effectiveness)\b',
    r'\b(reactive power|kvar|kvarh)\b',
    r'\b(cleanroom|office lighting|building lighting)\b',
    r'\b(penalty|tariff penalty|grid penalty|billing penalty|penalties|surcharge)\b',
    r'\b(bearing wear|air leak|leak detection|mechanical failure|motor failure|root cause|breakdown reason)\b',
]


def _is_analytical_question(question: str) -> bool:
    """
    Determine if a user question requires empirical database evidence.
    Educational, methodology, and explicitly unsupported concept questions (such as OEE,
    reactive power, or tariff penalties) can be answered without tool execution,
    while factual, quantitative, and operational data queries require verified tool evidence.
    """
    q_lower = question.lower().strip()
    # 1. Unsupported domain metrics: never require database tools (no tools exist for them)
    if any(re.search(pat, q_lower) for pat in UNSUPPORTED_DOMAINS):
        return False
    # 2. Educational/methodology queries without specific entity IDs
    is_edu = any(re.search(pat, q_lower) for pat in EDUCATIONAL_PATTERNS)
    has_specific_entity = bool(
        re.search(
            r'\b(in-tn-01|smt-l[12]|fal-l[12]|mtr-\w+|sph-\w+|\d{4}-\d{2}-\d{2}|yesterday|last (week|month|year))\b',
            q_lower,
        )
    )
    if is_edu and not has_specific_entity:
        return False
    # 3. Operational analytics indicators
    return any(re.search(pat, q_lower) for pat in ANALYTICAL_INDICATORS)


def _format_evidence_summary(evidence: List[ToolEvidence]) -> str:
    """Produce concise technical summary of executed tools and outcomes for prompt injection."""
    if not evidence:
        return "No tools executed."
    lines = []
    for item in evidence:
        status = "SUCCESS" if item.success else f"FAILED: {item.error}"
        lines.append(f"- Step {item.execution_order}: [{item.tool_name}] -> {status}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent Orchestration Coordinator
# ---------------------------------------------------------------------------

class IndustrialEnergyAgent:
    """
    Controlled ReAct AI Agent for the Industrial Energy Intelligence Platform.

    Enforces:
    - Maximum 5 tool executions per user request (hard Python gate).
    - Maximum 10 model generation calls to prevent infinite loops.
    - Strict JSON-action protocol validation via ActionParser.
    - Zero evaluation of model-generated code outside read_only_sql_query.
    - Tool evidence tracking and citation verification.
    - Sanitized error reporting without token or infrastructure leakage.
    """

    MAX_TOOL_EXECUTIONS = 5
    MAX_MODEL_CALLS = 10
    MAX_CORRECTIONS_PER_STEP = 2

    def __init__(
        self,
        domo_client: Optional[DomoClient] = None,
        max_tool_executions: int = MAX_TOOL_EXECUTIONS,
        max_model_calls: int = MAX_MODEL_CALLS,
        max_corrections_per_step: int = MAX_CORRECTIONS_PER_STEP,
        conversation_context: Optional[ConversationContext] = None,
    ):
        self.domo_client = domo_client
        self.max_tool_executions = min(max_tool_executions, self.MAX_TOOL_EXECUTIONS)
        self.max_model_calls = max_model_calls
        self.max_corrections_per_step = max_corrections_per_step
        self.conversation_context = conversation_context or ConversationContext()

    def _get_domo_client(self) -> DomoClient:
        """Resolve or lazily instantiate DomoClient."""
        if self.domo_client is not None:
            return self.domo_client
        return get_domo_client()

    def _validate_user_question(self, question: str) -> str:
        """Validate and clean user input."""
        if not question or not isinstance(question, str):
            raise AgentInputError("User question must be a non-empty string.")
        cleaned = question.strip()
        if not cleaned:
            raise AgentInputError("User question cannot be empty or whitespace only.")
        if len(cleaned) > 2000:
            raise AgentInputError("User question exceeds maximum allowed length of 2000 characters.")
        return cleaned

    async def run(
        self,
        user_question: str,
        history: Optional[List[Any]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResponse:
        """
        Execute an end-to-end controlled ReAct turn for the provided user question.

        Args:
            user_question: Natural language question about plant operations.
            history: Optional multi-turn conversation history.
            session_id: Optional session identifier for tracking.

        Returns:
            AgentResponse containing the final answer, evidence records, and execution counts.

        Raises:
            AgentInputError: If user question is invalid.
            AgentError: If unrecoverable execution or model error occurs.
        """
        clean_question = self._validate_user_question(user_question)

        # 0. Deterministic Greeting & Conversational Intent Detection
        # Pure greetings return assistant capabilities immediately without invoking analytical tools or LLM calls.
        if self.conversation_context.is_greeting(clean_question):
            return AgentResponse(
                answer=self.conversation_context.get_greeting_response(clean_question),
                tool_references=[],
                evidence=[],
                tool_executions_count=0,
                model_calls_count=0,
                limit_reached=False,
                verification_status="NO_ANALYTIC_CLAIMS",
                claims=[],
                verified_claims_count=0,
                unverified_claims_count=0,
            )

        client = self._get_domo_client()

        system_prompt = get_system_prompt()
        formatted_history = self.conversation_context.format_for_prompt(history)

        # Execution tracking state
        tool_executions_count = 0
        model_calls_count = 0
        evidence: List[ToolEvidence] = []
        step_history: List[Dict[str, Any]] = []

        # Step error / correction state
        correction_message: Optional[str] = None
        limit_reached_message: Optional[str] = None
        parse_corrections = 0
        grounding_corrections = 0
        citation_corrections = 0
        limit_reached = False

        while model_calls_count < self.max_model_calls:
            # 1. Assemble complete prompt for current ReAct iteration
            full_prompt = build_react_prompt(
                system_prompt=system_prompt,
                user_question=clean_question,
                conversation_history=formatted_history,
                step_history=step_history,
                correction_message=correction_message,
                limit_reached_message=limit_reached_message,
            )

            # Clear single-use notices after injecting into prompt
            correction_message = None
            limit_reached_message = None

            # 2. Invoke Domo API
            model_calls_count += 1
            try:
                domo_response = await client.generate_text(
                    prompt=full_prompt,
                )
                raw_output = domo_response.output
            except DomoAuthenticationError as e:
                logger.error("Domo authentication error during agent execution.")
                raise AgentError("AI service authentication failed. Please verify credentials.") from e
            except DomoRateLimitError as e:
                logger.warning("Domo rate limit encountered during agent execution.")
                raise AgentError("AI service rate limit reached. Please try again shortly.") from e
            except DomoTimeoutError as e:
                logger.warning("Domo request timed out during agent execution.")
                raise AgentError("AI service request timed out. Please try again.") from e
            except (DomoServerError, DomoConnectionError) as e:
                logger.error("Domo service error: %s", str(e))
                raise AgentError("AI service is currently unavailable. Please try again later.") from e
            except DomoError as e:
                logger.error("Domo client error: %s", str(e))
                raise AgentError("AI service encountered an unexpected error.") from e
            except Exception as e:
                logger.exception("Unexpected error communicating with AI service: %s", str(e))
                raise AgentError("AI service is currently unavailable. Please try again later.") from e

            # 3. Parse and validate model action
            try:
                action = parse_agent_action(raw_output)
            except (ActionParseError, ToolNotFoundError, ToolArgumentError) as parse_err:
                parse_corrections += 1
                logger.warning(
                    "Model action parsing failed (attempt %d/%d): %s",
                    parse_corrections,
                    self.max_corrections_per_step,
                    str(parse_err),
                )

                if parse_corrections <= self.max_corrections_per_step:
                    # Provide targeted correction feedback without executing any tool
                    correction_message = get_correction_prompt(str(parse_err))
                    continue
                else:
                    # Exceeded allowed correction attempts for this step
                    if evidence:
                        # Fallback: synthesize safe answer from evidence collected so far
                        summary = _format_evidence_summary(evidence)
                        return AgentResponse(
                            answer=(
                                "The analysis could not be fully completed due to model action formatting errors. "
                                f"However, the following preliminary evidence was successfully retrieved:\n\n{summary}"
                            ),
                            tool_references=[e.tool_name for e in evidence if e.success],
                            evidence=evidence,
                            tool_executions_count=tool_executions_count,
                            model_calls_count=model_calls_count,
                            limit_reached=limit_reached,
                            verification_status="PARTIALLY_VERIFIED" if evidence else "UNVERIFIED",
                            claims=[],
                            verified_claims_count=0,
                            unverified_claims_count=0,
                        )
                    raise AgentError(
                        f"Model failed to produce a valid action after {self.max_corrections_per_step} correction attempts: {str(parse_err)}"
                    ) from parse_err

            # Action successfully parsed; reset parse correction counter
            parse_corrections = 0

            # ---------------------------------------------------------------
            # 4. Handle Final Answer Action
            # ---------------------------------------------------------------
            if isinstance(action, FinalAnswerAction):
                # 4a. Numerical Grounding Enforcement
                is_analytical = _is_analytical_question(clean_question)
                successful_tools = [e for e in evidence if e.success]

                if is_analytical and not successful_tools:
                    grounding_corrections += 1
                    # Model attempted to answer an analytical/data query without successful tool execution
                    if grounding_corrections <= self.max_corrections_per_step:
                        correction_message = (
                            "CRITICAL REQUIREMENT: The user's query asks for analytical or factory operational data, "
                            "which requires empirical database evidence. You attempted to provide a direct final answer "
                            "without executing any analytics tools, or all attempted tool executions failed.\n"
                            "You must execute an appropriate registered tool (or read_only_sql_query) to retrieve "
                            "verified data before answering. If tools fail or data is missing, report that fact explicitly."
                        )
                        continue
                    else:
                        # Corrections exhausted: enforce safe unverified response to prevent hallucination
                        logger.warning(
                            "Agent attempted to bypass numerical grounding for analytical query '%s'. Returning safe unverified fallback.",
                            clean_question[:60],
                        )
                        return AgentResponse(
                            answer=(
                                "This question requires verified factory data from the operational database, "
                                "but no successful analytics tool execution was completed to ground the response. "
                                "To maintain strict numerical integrity and prevent ungrounded or fabricated metrics, "
                                "data-specific figures cannot be reported without successful tool execution. "
                                "Please verify system parameters or rephrase your request."
                            ),
                            tool_references=[],
                            evidence=evidence,
                            tool_executions_count=tool_executions_count,
                            model_calls_count=model_calls_count,
                            limit_reached=limit_reached,
                            verification_status="UNVERIFIED",
                            claims=[],
                            verified_claims_count=0,
                            unverified_claims_count=0,
                        )

                # 4b. Verify tool references: model must not claim tools that were never run or failed
                executed_tools: Set[str] = {e.tool_name for e in evidence if e.success}
                unexecuted_citations = [t for t in action.tool_references if t not in executed_tools]

                if unexecuted_citations:
                    citation_corrections += 1
                    if citation_corrections <= self.max_corrections_per_step:
                        correction_message = (
                            f"CRITICAL ERROR: Your 'tool_references' cited tool(s) {unexecuted_citations} "
                            f"which were NOT successfully executed during this turn. "
                            f"Successfully executed tools: {sorted(list(executed_tools)) if executed_tools else 'None'}.\n"
                            "You must strictly cite ONLY tools that were successfully executed. "
                            "Please output a corrected final answer now."
                        )
                        continue
                    else:
                        # Filter to truly executed tools to prevent hallucinated citations
                        valid_references = [t for t in action.tool_references if t in executed_tools]
                else:
                    valid_references = action.tool_references

                # 4c. Deterministic Numeric Claim Verification against authoritative tool evidence
                verification = verify_numeric_claims(
                    answer=action.answer,
                    evidence=evidence,
                    user_question=clean_question,
                )

                return AgentResponse(
                    answer=verification.final_answer,
                    tool_references=valid_references,
                    evidence=evidence,
                    tool_executions_count=tool_executions_count,
                    model_calls_count=model_calls_count,
                    limit_reached=limit_reached,
                    verification_status=verification.summary.status,
                    claims=[c.to_dict() for c in verification.claims],
                    verified_claims_count=verification.summary.verified_claims,
                    unverified_claims_count=verification.summary.unverified_claims,
                )

            # ---------------------------------------------------------------
            # 5. Handle Tool Call Action
            # ---------------------------------------------------------------
            elif isinstance(action, ToolCallAction):
                # Strict hard limit check: NEVER exceed 5 tool executions per turn
                if tool_executions_count >= self.max_tool_executions:
                    limit_reached = True
                    logger.warning(
                        "Tool execution limit of %d reached. Blocking tool '%s'.",
                        self.max_tool_executions,
                        action.tool_name,
                    )
                    evidence_summary = _format_evidence_summary(evidence)
                    limit_reached_message = get_limit_reached_prompt(evidence_summary)
                    continue

                # Execute the tool safely
                tool_executions_count += 1
                exec_order = tool_executions_count
                tool_name = action.tool_name
                arguments = action.arguments

                logger.info(
                    "Executing tool [%d/%d]: %s with args: %s",
                    exec_order,
                    self.max_tool_executions,
                    tool_name,
                    arguments,
                )

                try:
                    result = execute_tool(name=tool_name, args=arguments)
                    evidence_record = ToolEvidence(
                        execution_order=exec_order,
                        tool_name=tool_name,
                        arguments=arguments,
                        result=result,
                        success=True,
                    )
                    evidence.append(evidence_record)

                    # Serialize summarized view for prompt while keeping full output in ToolEvidence
                    llm_view = _prepare_tool_output_for_llm(tool_name, result)
                    serialized_res = _serialize_tool_output(llm_view)
                    step_history.append({
                        "action_raw": raw_output.strip(),
                        "tool_output": serialized_res,
                    })

                except (SQLValidationError, SQLExecutionError) as sql_err:
                    err_msg = str(sql_err)
                    logger.warning("Tool '%s' SQL execution failed: %s", tool_name, err_msg)
                    evidence_record = ToolEvidence(
                        execution_order=exec_order,
                        tool_name=tool_name,
                        arguments=arguments,
                        result=None,
                        success=False,
                        error=err_msg,
                    )
                    evidence.append(evidence_record)
                    step_history.append({
                        "action_raw": raw_output.strip(),
                        "tool_output": json.dumps({"status": "error", "message": err_msg}),
                    })

                except Exception as tool_err:
                    err_msg = f"Tool execution error: {str(tool_err)}"
                    logger.warning("Tool '%s' failed unexpectedly: %s", tool_name, err_msg)
                    evidence_record = ToolEvidence(
                        execution_order=exec_order,
                        tool_name=tool_name,
                        arguments=arguments,
                        result=None,
                        success=False,
                        error=err_msg,
                    )
                    evidence.append(evidence_record)
                    step_history.append({
                        "action_raw": raw_output.strip(),
                        "tool_output": json.dumps({"status": "error", "message": err_msg}),
                    })

                # If we just reached the 5-tool limit, proactively prepare limit notice for next turn
                if tool_executions_count >= self.max_tool_executions:
                    limit_reached = True
                    evidence_summary = _format_evidence_summary(evidence)
                    limit_reached_message = get_limit_reached_prompt(evidence_summary)

        # Loop exhausted without final answer
        if evidence:
            summary = _format_evidence_summary(evidence)
            return AgentResponse(
                answer=(
                    f"The reasoning process reached the maximum limit of {self.max_model_calls} model calls. "
                    f"Evidence collected so far:\n\n{summary}"
                ),
                tool_references=[e.tool_name for e in evidence if e.success],
                evidence=evidence,
                tool_executions_count=tool_executions_count,
                model_calls_count=model_calls_count,
                limit_reached=True,
                verification_status="PARTIALLY_VERIFIED" if any(e.success for e in evidence) else "UNVERIFIED",
                claims=[],
                verified_claims_count=0,
                unverified_claims_count=0,
            )

        raise MaxModelCallsError(
            f"Agent reached maximum model reasoning limit of {self.max_model_calls} calls without resolving the question."
        )

