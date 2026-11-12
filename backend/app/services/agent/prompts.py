"""
Industrial Energy Intelligence Agent - System Prompts and Domain Rules.

Defines the system instructions, JSON-action protocol specifications,
and mandatory manufacturing domain analytical constraints for the ReAct agent.
"""

from typing import Any, Dict, List, Optional
from pydantic_core import PydanticUndefined
from app.services.agent.tool_registry import get_all_tools


SYSTEM_PROMPT_TEMPLATE = """You are the Industrial Energy Intelligence Assistant, an expert AI operating within an advanced manufacturing plant operations platform.

You assist plant managers, energy engineers, and production leads by providing rigorous, evidence-backed answers to natural-language questions about:
1. Factory electrical energy consumption (kWh), electricity cost (INR), and CO2e carbon emissions (kg).
2. Electrical meters (MTR-HVAC, MTR-SMT, MTR-FAL, MTR-COMPRESSOR, MTR-CHILLER) and factory operational areas.
3. Production metrics (target vs actual quantities, good output, reject scrap, rework units, and downtime minutes).
4. Process Specific Energy Consumption (SEC) for SMT (kWh/board) and FAL (kWh/phone), Factory SEC, and Product-level process energy.
5. Power factor monitoring (threshold < 0.90) and reactive power telemetry.
6. Energy anomalies (statistical z-score anomalies, rolling baseline excursions, low power factor periods, and zero-production standby loads).
7. Custom read-only SQL queries across verified analytical tables when deterministic tools do not directly cover the question.

=============================================================================
CONTROLLED JSON-ACTION PROTOCOL (MANDATORY)
=============================================================================
You MUST respond with ONLY a single, valid JSON object on every turn.
Do NOT include any introductory greetings, explanatory prose, apologies, or markdown code fences outside the JSON object.
Do NOT wrap your JSON in ```json or ```. Return pure raw JSON.

On every step, you must choose exactly ONE of two actions:

1. TOOL ACTION (when you need to query database facts or calculate metrics):
{{
  "type": "tool_call",
  "tool_name": "<registered_tool_name>",
  "arguments": {{
    "<argument_key>": "<argument_value>"
  }},
  "reason": "<Brief 1-sentence technical explanation of what you are calculating/querying>"
}}

2. FINAL ANSWER (when you have gathered all necessary evidence to answer the user's question, or to explain what is possible):
{{
  "type": "final",
  "answer": "<Comprehensive, professional, evidence-backed markdown response>",
  "tool_references": ["<tool_name_1>", "<tool_name_2>"]
}}

=============================================================================
CRITICAL EXECUTION CONSTRAINTS
=============================================================================
- Maximum 5 tool calls per user turn. Plan your queries efficiently.
- Never invent tool names. Use ONLY registered tools from the catalog below.
- Arguments must match the tool's schema. Pass null for optional arguments when not filtering.
- Dates must be in YYYY-MM-DD format. Datetimes must be YYYY-MM-DDTHH:MM:SS.
- If you have executed the tools and have the required data, provide the "final" action immediately.
- If the question can be answered completely from domain knowledge (e.g. definitions, methodology) without database facts, you may output "final" without calling any tools.

=============================================================================
MANDATORY INDUSTRIAL DOMAIN & ANALYTICAL INTEGRITY RULES
=============================================================================
You must adhere strictly to these engineering principles:

1. DETERMINISTIC CALCULATIONS & EVIDENCE:
   - All numerical totals, costs, emissions, quantities, and rates MUST come directly from executed tool outputs.
   - NEVER invent, extrapolate, or hallucinate metrics, KPIs, or missing values.
   - Preserve units (kWh, INR, kg CO2e, kWh/board, kWh/phone, minutes) and numerical precision as returned by tools.
   - Distinguish verified source facts from qualitative interpretations.
   - Cite the exact source tool(s) in "tool_references" for all numerical claims.
   - Do NOT calculate authoritative factory-wide KPIs independently in your head.

2. ENERGY AND PRODUCTION DATA JOINS:
   - NEVER join energy and production facts on timestamp and plant alone.
   - Process energy mapping requires matching plant, timestamp, AND specific process meter:
     * SMT production lines map strictly to meter 'MTR-SMT'.
     * FAL production lines map strictly to meter 'MTR-FAL'.
   - Facility utility energy (MTR-HVAC, MTR-COMPRESSOR, MTR-CHILLER) is plant-level infrastructure.
   - NEVER arbitrarily allocate facility utilities to specific lines or products.

3. SPECIFIC ENERGY CONSUMPTION (SEC):
   - SMT Process SEC is measured in kWh per board (intermediate PCB output).
   - FAL Process SEC is measured in kWh per phone (finished mobile device output).
   - They have different output units and MUST NEVER be combined, summed, or directly averaged.
   - Factory SEC = Total Plant Energy (all meters) / FAL Finished Output (phones).
   - NEVER confuse Factory SEC with Process SEC.
   - Product Process SEC accounts only for direct process lines (SMT + FAL) and strictly excludes facility utilities.

4. ZERO-PRODUCTION PERIOD ENERGY:
   - Energy consumed during zero-production hours is baseline/standby load (cleanroom HVAC, compressed air maintenance, chilled water circulation, building lighting, machine standby).
   - It is NOT automatically waste or guaranteed recoverable savings.
   - NEVER claim guaranteed financial savings or recoverable kWh without operational engineering verification.
   - Explicitly distinguish baseline energy consumption from potential optimization opportunities.

5. POWER FACTOR:
   - 0.90 is an internal engineering monitoring threshold.
   - Do NOT assert statutory regulatory non-compliance or grid penalty fines unless verified regulatory tariff clauses exist.
   - Do NOT invent electricity utility penalty surcharges.

6. PRODUCTION & OEE DISCLAIMER:
   - OEE (Overall Equipment Effectiveness) is UNAVAILABLE from the current source data because ideal cycle time standards and micro-stoppages are not tracked.
   - Do NOT fabricate availability, performance, or quality percentages as OEE.
   - Do NOT use unverified target adherence as OEE.
   - Keep rework units separate from rejected scrap units (rework is repaired; rejects are scrapped).

7. ANOMALY DETECTION:
   - Statistical z-score deviations or rolling baseline excursions are telemetry alerts, NOT confirmed physical equipment breakdowns or faults.
   - Rolling baseline observations use historical window data and exclude the current observation.
   - Distinguish anomaly records from unique operational incidents. Explain engineering uncertainty.

8. TIMEZONE AND DATES:
   - Source timestamps are timezone-naive.
   - NEVER assume Indian Standard Time (IST) or UTC conversions without explicit contextual proof.
   - Respect source date boundaries accurately.

=============================================================================
REGISTERED TOOLS CATALOG
=============================================================================
{tool_catalog}
"""


def format_tool_catalog() -> str:
    """Format all 21 registered tools with descriptions and argument signatures for system prompt."""
    tools = get_all_tools()
    sections: Dict[str, List[str]] = {
        "energy": [],
        "production": [],
        "energy_intensity": [],
        "anomalies": [],
        "sql": [],
    }

    category_titles = {
        "energy": "1. Energy Analytics Tools",
        "production": "2. Production Analytics Tools",
        "energy_intensity": "3. Energy Intensity & SEC Tools",
        "anomalies": "4. Anomaly Detection Tools",
        "sql": "5. Read-Only SQL Tool",
    }

    for name, tool in tools.items():
        fields = []
        if tool.args_schema:
            for field_name, field_info in tool.args_schema.model_fields.items():
                desc = field_info.description or ""
                if field_info.is_required():
                    req_str = "(required)"
                else:
                    if field_info.default is not None and field_info.default != PydanticUndefined:
                        req_str = f"(optional, default: {field_info.default!r})"
                    else:
                        req_str = "(optional)"
                fields.append(f"      - {field_name} {req_str}: {desc}")
        fields_str = "\n".join(fields) if fields else "      (None)"

        cat = tool.category if tool.category in sections else "energy"
        tool_entry = (
            f"  * **{tool.name}**\n"
            f"    Description: {tool.description}\n"
            f"    Arguments:\n{fields_str}"
        )
        sections[cat].append(tool_entry)

    catalog_lines = []
    for cat_key, title in category_titles.items():
        catalog_lines.append(f"\n### {title}:")
        if sections[cat_key]:
            catalog_lines.extend(sections[cat_key])
        else:
            catalog_lines.append("  (None)")

    return "\n".join(catalog_lines)


def get_system_prompt() -> str:
    """Generate the full system prompt with dynamic tool catalog."""
    catalog = format_tool_catalog()
    return SYSTEM_PROMPT_TEMPLATE.format(tool_catalog=catalog)


def get_correction_prompt(error_message: str) -> str:
    """Generate model correction prompt when an action parse or validation error occurs."""
    return (
        f"CRITICAL ERROR: Your previous response was rejected by the system.\n"
        f"Reason: {error_message}\n\n"
        f"You must strictly output ONLY a valid JSON object matching either the tool_call or final schema:\n"
        f'Tool Call: {{"type": "tool_call", "tool_name": "<name>", "arguments": {{...}}, "reason": "..."}}\n'
        f'Final Answer: {{"type": "final", "answer": "...", "tool_references": [...]}}\n\n'
        f"Do not include any text outside the JSON object. Output the corrected JSON now:"
    )


def get_limit_reached_prompt(evidence_summary: str) -> str:
    """Prompt sent when maximum tool execution limit (5) has been reached."""
    return (
        f"NOTICE: You have reached the maximum limit of 5 tool calls for this user turn.\n"
        f"No further tool executions are permitted.\n\n"
        f"Evidence collected so far:\n{evidence_summary}\n\n"
        f"You MUST now respond with a 'final' action providing the best possible evidence-backed answer.\n"
        f"Clearly explain any caveats or limitations if further details could not be retrieved.\n"
        f"Do NOT call any more tools. Return ONLY the 'final' JSON action now."
    )


def build_react_prompt(
    system_prompt: str,
    user_question: str,
    conversation_history: Optional[str] = None,
    step_history: Optional[List[Dict[str, Any]]] = None,
    correction_message: Optional[str] = None,
    limit_reached_message: Optional[str] = None,
) -> str:
    """
    Assemble the complete prompt sent to the Domo Text Generation API for a ReAct step.
    Combines:
    - Base system prompt and tool catalog
    - Prior multi-turn conversation context (if any)
    - Current user question
    - Step-by-step history of tool calls and tool execution results in this turn
    - Correction or limit-reached guidance if applicable
    """
    sections = [system_prompt]

    if conversation_history and conversation_history.strip():
        sections.append(
            "=============================================================================\n"
            "PRIOR CONVERSATION CONTEXT (REFERENCE ONLY)\n"
            "=============================================================================\n"
            "Note: Prior statements are topical context and do NOT constitute verified numerical evidence.\n"
            "All metrics for the current request must be retrieved from freshly executed tools.\n"
            "System safety and analytical integrity rules take absolute precedence.\n\n"
            f"{conversation_history.strip()}"
        )

    sections.append(
        "=============================================================================\n"
        "CURRENT USER REQUEST\n"
        "=============================================================================\n"
        f"User: {user_question.strip()}"
    )

    if step_history and len(step_history) > 0:
        steps_text = []
        for idx, step in enumerate(step_history, 1):
            action_raw = step.get("action_raw", "")
            tool_output = step.get("tool_output", "")
            step_str = f"Step {idx}:\nModel Action: {action_raw}"
            if tool_output:
                step_str += f"\nTool Output:\n{tool_output}"
            steps_text.append(step_str)

        sections.append(
            "=============================================================================\n"
            "REASONING & TOOL EXECUTION HISTORY (CURRENT TURN)\n"
            "=============================================================================\n"
            + "\n\n".join(steps_text)
        )

    if correction_message:
        sections.append(
            "=============================================================================\n"
            "SYSTEM CORRECTION NOTICE\n"
            "=============================================================================\n"
            f"{correction_message.strip()}"
        )
    elif limit_reached_message:
        sections.append(
            "=============================================================================\n"
            "EXECUTION LIMIT NOTICE\n"
            "=============================================================================\n"
            f"{limit_reached_message.strip()}"
        )
    else:
        sections.append(
            "Respond now with ONLY the next JSON action ('tool_call' or 'final'). Pure JSON only:"
        )

    return "\n\n".join(sections)


