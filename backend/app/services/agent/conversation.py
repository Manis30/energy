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
