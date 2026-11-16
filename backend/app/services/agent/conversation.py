"""
Conversation Context Handler for Industrial Energy Intelligence Agent.

Manages multi-turn conversation context within a user interaction:
- Formats prior user/assistant turns with strict analytical boundaries.
- Emphasizes that prior assistant responses are conversational references only,
  not verified numerical facts.
- Explicitly prevents user prompt-injection attempts to override system safety rules.
- Integrates cleanly with LangChain Core message abstractions (HumanMessage, AIMessage).
- Implements bounded message history to prevent context overflow.
- Excludes internal tool reasoning steps from external conversational history.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def _sanitize_turn_content(content: str) -> str:
    """Sanitize conversation text to prevent history-based prompt or tool injection."""
    if not content:
        return ""
    sanitized = content
    # Strip attempts to inject simulated tool output blocks or system notices
    sanitized = re.sub(
        r'\[TOOL_OUTPUT\].*?(\[\/TOOL_OUTPUT\]|$)',
        '[prior tool output reference omitted]',
        sanitized,
        flags=re.DOTALL | re.IGNORECASE,
    )
    sanitized = re.sub(
        r'(SYSTEM CORRECTION NOTICE|EXECUTION LIMIT NOTICE|CRITICAL ERROR)',
        '[system message reference omitted]',
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized.strip()


@dataclass
class ConversationTurn:
    """Represents a single user or assistant conversational message."""
    role: Literal["user", "assistant"]
    content: str

    def to_langchain_message(self) -> BaseMessage:
        """Convert to LangChain message instance."""
        if self.role == "user":
            return HumanMessage(content=self.content)
        return AIMessage(content=self.content)

    @classmethod
    def from_langchain_message(cls, message: BaseMessage) -> "ConversationTurn":
        """Construct from LangChain message instance."""
        if isinstance(message, HumanMessage):
            return cls(role="user", content=str(message.content))
        elif isinstance(message, AIMessage):
            return cls(role="assistant", content=str(message.content))
        else:
            role = "user" if message.type in ("human", "user") else "assistant"
            return cls(role=role, content=str(message.content))


# ---------------------------------------------------------------------------
# Conversational Greeting & Intent Classification
# ---------------------------------------------------------------------------

GREETING_PHRASES = {
    "hi", "hii", "hiii", "hey", "heyy", "heya",
    "hello", "helloo", "hola", "howdy", "namaste", "vanakkam",
    "greetings", "salutations",
    "good morning", "good afternoon", "good evening", "good day",
    "morning", "afternoon", "evening",
    "sup", "whats up", "what's up",
    "how are you", "how are you doing", "how r u",
    "who are you", "who are u", "what are you",
    "what can you do", "what do you do", "capabilities", "help",
    "hi there", "hello there", "hey there",
    "hi assistant", "hello assistant", "hey assistant",
}

ACKNOWLEDGMENT_PHRASES = {
    "thanks", "thank you", "thx", "thank you so much",
    "thanks a lot", "many thanks", "appreciate it", "cheers",
    "bye", "goodbye", "see you", "see ya",
}

# Explicit analytical keywords. If ANY of these appear in the query, it is an analytical question, NOT a greeting.
ANALYTICAL_TOKENS = {
    # Energy & Power
    "energy", "power", "pf", "powerfactor", "factor", "kwh", "mwh", "kw", "mw", "voltage", "current",
    "reactive", "apparent", "active", "consumption", "usage",
    # Intensity
    "sec", "intensity", "specific",
    # Cost & Carbon
    "cost", "inr", "rs", "rupee", "rupees", "tariff", "bill", "co2", "co2e", "emission", "emissions", "carbon",
    # Production
    "production", "output", "qty", "quantity", "target", "actual", "good", "reject", "rejects",
    "rework", "scrap", "defect", "defects", "yield",
    # Stoppage & Equipment
    "downtime", "stoppage", "idle", "standby", "line", "lines", "smt", "fal", "shift",
    "hvac", "compressor", "chiller", "meter", "meters",
    # Identifiers
    "plant", "plants", "in-tn-01", "in-ka-01", "mtr-smt", "mtr-fal", "mtr-hvac", "mtr-compressor", "mtr-chiller",
    # Anomaly
    "anomaly", "anomalies", "outlier", "outliers", "zscore", "deviation", "spike", "baseline",
    # Analytical intent words
    "trend", "trends", "compare", "comparison", "calculate", "stat", "stats", "statistics",
    "reconcil", "reconciliation", "variance", "audit", "summary", "report", "breakdown",
    "highest", "lowest", "average", "total", "peak", "max", "min",
    # Time boundaries
    "yesterday", "today", "tomorrow", "week", "month", "year", "hourly", "daily",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
    "2024", "2025", "2026", "2027",
}


def is_conversational_greeting(query: str) -> bool:
    """
    Deterministically identify whether a user message is a pure conversational greeting or pleasantry.

    Returns False if the message contains ANY analytical, operational, or domain-specific keywords
    (such as 'PF', 'SEC', 'energy', 'plant', 'cost', 'anomalies'), ensuring that concise operational
    queries like 'PF?' or 'SEC?' are always routed to the analytical ReAct agent.
    """
    if not query or not isinstance(query, str):
        return False

    cleaned = query.strip()
    if not cleaned:
        return False

    # Normalize: lowercase, replace non-alphanumeric (except hyphen) with space
    normalized = re.sub(r'[^a-zA-Z0-9\s-]', ' ', cleaned.lower())
    words = [w for w in normalized.split() if w]
    if not words:
        return False

    # 1. Exact phrase matches (e.g. 'good morning', 'hello', 'hii', 'what can you do')
    normalized_phrase = " ".join(words)
    if normalized_phrase in GREETING_PHRASES or normalized_phrase in ACKNOWLEDGMENT_PHRASES:
        return True

    # 2. Guardrail: If ANY word or token matches an analytical keyword, it is NOT a greeting
    words_set = set(words)
    for token in ANALYTICAL_TOKENS:
        if token in words_set or token in normalized_phrase:
            return False

    # 3. Single-word greeting check
    if len(words) == 1 and (words[0] in GREETING_PHRASES or words[0] in ACKNOWLEDGMENT_PHRASES):
        return True

    # 4. Short conversational openers <= 3 words (e.g. 'hi there assistant', 'hey team')
    if len(words) <= 3 and words[0] in {"hi", "hii", "hiii", "hey", "heyy", "hello", "hola", "greetings"}:
        return True

    return False


def get_greeting_response(query: str = "") -> str:
    """Generate a clean, structured assistant introduction without executing analytical tools."""
    cleaned_lower = query.lower().strip() if query else ""
    if any(k in cleaned_lower for k in ("thank", "thx", "appreciate", "cheers", "bye", "goodbye")):
        return (
            "You're welcome! Let me know if you would like any analysis on factory energy consumption, "
            "production outputs, Specific Energy Consumption (SEC), power factor monitoring, or detected anomalies."
        )

    return (
        "Hello! 👋 I'm the **Industrial Energy Intelligence Assistant** for your manufacturing plant operations platform.\n\n"
        "I can help you analyze factory telemetry, energy consumption, and production metrics. You can ask me questions such as:\n\n"
        "- ⚡ **Energy Consumption:** *\"What was total energy consumption and cost across plants last week?\"*\n"
        "- 📊 **Production & Lines:** *\"Show me production output and reject count for SMT line.\"*\n"
        "- 🔋 **Specific Energy Consumption:** *\"What is the SEC for SMT and FAL processes?\"*\n"
        "- 📉 **Power Factor:** *\"Are there any meters with a power factor below 0.90?\"*\n"
        "- 🚨 **Anomalies:** *\"Were there any statistical energy anomalies detected recently?\"*\n"
        "- 🏭 **Plant Comparisons:** *\"Compare energy intensity between IN-TN-01 and IN-KA-01.\"*\n\n"
        "How can I assist you with factory telemetry today?"
    )


class ConversationContext:
    """
    Manages bounded multi-turn conversation context for the agent.

    Enforces:
    - Bounded history limit (default 10 turns).
    - Separation of user-visible conversation from internal tool execution traces.
    - Zero trust of prior numerical claims without re-verification.
    """

    def __init__(self, max_history_turns: int = 10):
        self.max_history_turns = max_history_turns

    def sanitize_history(
        self,
        history: Optional[List[Union[ConversationTurn, BaseMessage, Dict[str, Any]]]] = None,
    ) -> List[ConversationTurn]:
        """Normalize and cap conversation history into a list of ConversationTurn objects."""
        if not history:
            return []

        turns: List[ConversationTurn] = []
        for item in history:
            if isinstance(item, ConversationTurn):
                clean_content = _sanitize_turn_content(item.content)
                turns.append(ConversationTurn(role=item.role, content=clean_content))
            elif isinstance(item, BaseMessage):
                turn = ConversationTurn.from_langchain_message(item)
                turn.content = _sanitize_turn_content(turn.content)
                turns.append(turn)
            elif isinstance(item, dict):
                role = item.get("role", "user")
                if role not in ("user", "assistant"):
                    role = "user"
                content = _sanitize_turn_content(str(item.get("content", "")))
                turns.append(ConversationTurn(role=role, content=content))

        # Enforce history limit by keeping the most recent turns
        if len(turns) > self.max_history_turns:
            turns = turns[-self.max_history_turns:]

        return turns

    def format_for_prompt(
        self,
        history: Optional[List[Union[ConversationTurn, BaseMessage, Dict[str, Any]]]] = None,
    ) -> str:
        """Format prior conversation history into a sanitized text block for prompt injection."""
        clean_turns = self.sanitize_history(history)
        if not clean_turns:
            return ""

        lines = []
        for turn in clean_turns:
            speaker = "User" if turn.role == "user" else "Assistant (Historical dialogue context only)"
            lines.append(f"{speaker}: {turn.content.strip()}")

        return "\n".join(lines)

    def is_greeting(self, query: str) -> bool:
        """Check if user query is a conversational greeting or pleasantry."""
        return is_conversational_greeting(query)

    def get_greeting_response(self, query: str = "") -> str:
        """Return standardized conversational greeting response."""
        return get_greeting_response(query)

