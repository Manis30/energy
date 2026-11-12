"""
Unit tests for strict JSON action parsing and validation.

Verifies:
- Valid tool calls and final answers.
- Code fence extraction and pure JSON enforcement.
- Syntax errors and non-object JSON roots.
- Missing required fields and unexpected extra fields.
- Tool existence verification against TOOL_REGISTRY.
- Tool argument validation against Pydantic schemas (dates, ranges, types).
"""

import unittest

from app.services.agent.action_parser import (
    ActionParseError,
    FinalAnswerAction,
    ToolArgumentError,
    ToolCallAction,
    ToolNotFoundError,
    parse_agent_action,
)


class TestActionParser(unittest.TestCase):
    """Test suite verifying strict JSON action parsing and schema validation."""

    def test_valid_tool_call_pure_json(self):
        raw = """{
            "type": "tool_call",
            "tool_name": "energy_summary",
            "arguments": {
                "plant_id": "IN-TN-01",
                "start_date": "2026-08-01",
                "end_date": "2026-10-31"
            },
            "reason": "Retrieve verified energy totals for Q3."
        }"""
        action = parse_agent_action(raw)
        self.assertIsInstance(action, ToolCallAction)
        self.assertEqual(action.tool_name, "energy_summary")
        self.assertEqual(action.arguments["plant_id"], "IN-TN-01")
        self.assertEqual(action.arguments["start_date"], "2026-08-01")
        self.assertEqual(action.reason, "Retrieve verified energy totals for Q3.")

    def test_valid_tool_call_markdown_fenced(self):
        raw = """```json
{
    "type": "tool_call",
    "tool_name": "production_summary",
    "arguments": {
        "plant_id": "IN-TN-01",
        "line_id": "SMT-L1"
    }
}
```"""
        action = parse_agent_action(raw)
        self.assertIsInstance(action, ToolCallAction)
        self.assertEqual(action.tool_name, "production_summary")
        self.assertEqual(action.arguments.get("line_id"), "SMT-L1")
        self.assertIsNone(action.reason)

    def test_valid_final_answer(self):
        raw = """{
            "type": "final",
            "answer": "The total consumption was 1,958,088.31 kWh costing INR 16,154,228.24.",
            "tool_references": ["energy_summary"]
        }"""
        action = parse_agent_action(raw)
        self.assertIsInstance(action, FinalAnswerAction)
        self.assertIn("1,958,088.31 kWh", action.answer)
        self.assertEqual(action.tool_references, ["energy_summary"])

    def test_valid_final_answer_no_tools(self):
        raw = """{
            "type": "final",
            "answer": "OEE is unavailable because planned operational time is not recorded in telemetry.",
            "tool_references": []
        }"""
        action = parse_agent_action(raw)
        self.assertIsInstance(action, FinalAnswerAction)
        self.assertEqual(action.tool_references, [])

    def test_invalid_json_syntax(self):
        raw = '{"type": "tool_call", "tool_name": "energy_summary", invalid_syntax}'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_empty_string(self):
        with self.assertRaises(ActionParseError):
            parse_agent_action("")

    def test_non_object_json_root(self):
        raw = '["tool_call", "energy_summary"]'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_prose_surrounding_json(self):
        raw = 'Sure, here is the tool call:\n{"type": "tool_call", "tool_name": "energy_summary", "arguments": {}}'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_missing_type_field(self):
        raw = '{"tool_name": "energy_summary", "arguments": {}}'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_unknown_action_type(self):
        raw = '{"type": "execute_code", "tool_name": "energy_summary"}'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_unknown_tool_name(self):
        raw = '{"type": "tool_call", "tool_name": "non_existent_tool", "arguments": {}}'
        with self.assertRaises(ToolNotFoundError):
            parse_agent_action(raw)

    def test_unexpected_fields_in_tool_call(self):
        raw = """{
            "type": "tool_call",
            "tool_name": "energy_summary",
            "arguments": {},
            "unexpected_extra_field": "disallowed"
        }"""
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_unexpected_fields_in_final_answer(self):
        raw = """{
            "type": "final",
            "answer": "Here is the result",
            "tool_references": [],
            "extra_field": 42
        }"""
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_missing_required_arguments_for_sql_tool(self):
        raw = '{"type": "tool_call", "tool_name": "read_only_sql_query", "arguments": {}}'
        with self.assertRaises(ToolArgumentError):
            parse_agent_action(raw)

    def test_malformed_date_format(self):
        raw = """{
            "type": "tool_call",
            "tool_name": "energy_summary",
            "arguments": {
                "start_date": "not-a-valid-date"
            }
        }"""
        with self.assertRaises(ToolArgumentError):
            parse_agent_action(raw)

    def test_invalid_date_range_start_after_end(self):
        raw = """{
            "type": "tool_call",
            "tool_name": "energy_summary",
            "arguments": {
                "start_date": "2026-10-31",
                "end_date": "2026-08-01"
            }
        }"""
        with self.assertRaises(ToolArgumentError):
            parse_agent_action(raw)

    def test_arguments_not_a_dictionary(self):
        raw = '{"type": "tool_call", "tool_name": "energy_summary", "arguments": "invalid_string"}'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_final_answer_empty_whitespace_only(self):
        raw = '{"type": "final", "answer": "   \n\t  ", "tool_references": []}'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)

    def test_final_answer_tool_references_not_strings(self):
        raw = '{"type": "final", "answer": "Analysis complete", "tool_references": [123, 456]}'
        with self.assertRaises(ActionParseError):
            parse_agent_action(raw)


if __name__ == "__main__":
    unittest.main()
