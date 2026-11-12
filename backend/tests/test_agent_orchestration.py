"""
Unit tests for ReAct agent orchestration coordinator.

Verifies:
- Simple question answered without tools (0 tools).
- Single deterministic tool execution.
- Multiple sequential tool executions with evidence tracking.
- Strict enforcement of maximum 5 tool calls (hard Python limit).
- Sixth tool execution strictly blocked.
- Model-call limit enforcement.
- Safe handling of tool failures and database errors.
- Sanitized handling of Domo API failures (auth, rate-limit, timeout, server).
- Self-correction of malformed model JSON and invalid tool arguments.
- Rejection/correction of unexecuted tool citations in final answers.
"""

from decimal import Decimal
import unittest
from unittest.mock import AsyncMock, patch

from app.services.agent.agent import (
    AgentError,
    AgentInputError,
    AgentResponse,
    IndustrialEnergyAgent,
    MaxModelCallsError,
    ToolEvidence,
)
from app.services.agent.domo_client import (
    DomoAuthenticationError,
    DomoClient,
    DomoRateLimitError,
    DomoServerError,
    DomoTextGenerationResponse,
    DomoTimeoutError,
)


class MockDomoClient:
    """Mock DomoClient returning pre-configured sequential outputs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.recorded_prompts = []

    async def generate_text(self, prompt: str, session_id=None, **kwargs):
        self.call_count += 1
        self.recorded_prompts.append(prompt)
        if not self.responses:
            raise RuntimeError(f"MockDomoClient exhausted all configured responses (called {self.call_count} times).")
        output = self.responses.pop(0)
        return DomoTextGenerationResponse(
            output=output,
            model="mock-domo-model",
            raw={"output": output},
        )


class TestAgentOrchestration(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying end-to-end agent orchestration logic."""

    async def test_input_validation(self):
        agent = IndustrialEnergyAgent(domo_client=MockDomoClient([]))
        with self.assertRaises(AgentInputError):
            await agent.run("")
        with self.assertRaises(AgentInputError):
            await agent.run("   \n\t  ")
        with self.assertRaises(AgentInputError):
            await agent.run("A" * 2500)

    async def test_zero_tools_pure_answer(self):
        """Domain question answered directly without querying database tools."""
        final_json = """{
            "type": "final",
            "answer": "OEE is unavailable because planned operating time and micro-stoppages are not tracked.",
            "tool_references": []
        }"""
        mock_client = MockDomoClient([final_json])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        response = await agent.run("Can you provide OEE for Line 1?")
        self.assertEqual(mock_client.call_count, 1)
        self.assertEqual(response.tool_executions_count, 0)
        self.assertEqual(len(response.evidence), 0)
        self.assertEqual(response.tool_references, [])
        self.assertIn("OEE is unavailable", response.answer)

    async def test_one_tool_execution(self):
        """Execute one tool and synthesize evidence-backed answer."""
        tool_call_json = """{
            "type": "tool_call",
            "tool_name": "energy_summary",
            "arguments": {
                "plant_id": "IN-TN-01"
            },
            "reason": "Retrieve total plant energy metrics."
        }"""
        final_json = """{
            "type": "final",
            "answer": "Plant IN-TN-01 consumed 1,180,450.25 kWh with an electricity cost of INR 9,738,714.50.",
            "tool_references": ["energy_summary"]
        }"""

        mock_client = MockDomoClient([tool_call_json, final_json])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {
                "total_consumption_kwh": Decimal("1180450.2500"),
                "total_cost_inr": Decimal("9738714.50"),
                "total_co2e_kg": Decimal("967969.21"),
                "avg_power_factor": Decimal("0.9250"),
                "total_readings": 11040,
                "distinct_hours": 2208,
            }

            response = await agent.run("What was the total energy consumption for Tamil Nadu plant?")

            self.assertEqual(mock_client.call_count, 2)
            self.assertEqual(response.tool_executions_count, 1)
            self.assertEqual(len(response.evidence), 1)
            self.assertEqual(response.tool_references, ["energy_summary"])

            ev = response.evidence[0]
            self.assertEqual(ev.execution_order, 1)
            self.assertEqual(ev.tool_name, "energy_summary")
            self.assertTrue(ev.success)
            self.assertEqual(ev.arguments["plant_id"], "IN-TN-01")
            self.assertIn("1,180,450.25 kWh", response.answer)

    async def test_multiple_sequential_tools(self):
        """Execute two tools in sequence and combine results in final answer."""
        tool_1 = """{
            "type": "tool_call",
            "tool_name": "energy_summary",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        tool_2 = """{
            "type": "tool_call",
            "tool_name": "production_summary",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        final = """{
            "type": "final",
            "answer": "Plant IN-TN-01 consumed 1,180,450 kWh and produced 245,000 units.",
            "tool_references": ["energy_summary", "production_summary"]
        }"""

        mock_client = MockDomoClient([tool_1, tool_2, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.side_effect = [
                {"total_consumption_kwh": 1180450.0},
                {"actual_quantity": 245000},
            ]

            response = await agent.run("Compare energy and production for IN-TN-01.")

            self.assertEqual(mock_client.call_count, 3)
            self.assertEqual(response.tool_executions_count, 2)
            self.assertEqual(len(response.evidence), 2)
            self.assertEqual(response.evidence[0].tool_name, "energy_summary")
            self.assertEqual(response.evidence[1].tool_name, "production_summary")
            self.assertEqual(response.tool_references, ["energy_summary", "production_summary"])

    async def test_max_five_tool_executions_enforced(self):
        """Enforce strict hard cap of 5 tool executions per turn."""
        tool_actions = [
            """{"type": "tool_call", "tool_name": "energy_summary", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "production_summary", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "energy_by_meter", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "production_by_line", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "process_energy_intensity", "arguments": {}}""",
            # 6th tool call from model
            """{"type": "tool_call", "tool_name": "factory_energy_intensity", "arguments": {}}""",
            # Final answer after being notified limit reached
            """{"type": "final", "answer": "Analysis capped at 5 tools.", "tool_references": ["energy_summary", "production_summary", "energy_by_meter", "production_by_line", "process_energy_intensity"]}""",
        ]

        mock_client = MockDomoClient(tool_actions)
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {"status": "ok"}

            response = await agent.run("Perform exhaustive deep analysis.")

            # Exactly 5 executions occurred; the 6th tool was blocked
            self.assertEqual(mock_exec.call_count, 5)
            self.assertEqual(response.tool_executions_count, 5)
            self.assertEqual(len(response.evidence), 5)
            self.assertTrue(response.limit_reached)

            # Check that factory_energy_intensity was never executed
            executed_names = [e.tool_name for e in response.evidence]
            self.assertNotIn("factory_energy_intensity", executed_names)

    async def test_sixth_execution_blocked_when_model_insists(self):
        """Verify that even if model repeatedly requests tools after limit, no 6th execution occurs."""
        tool_actions = [
            """{"type": "tool_call", "tool_name": "energy_summary", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "production_summary", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "energy_by_meter", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "production_by_line", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "process_energy_intensity", "arguments": {}}""",
            # Model tries calling tools repeatedly after 5th
            """{"type": "tool_call", "tool_name": "factory_energy_intensity", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "product_process_energy", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "zero_production_period_energy", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "low_power_factor_anomalies", "arguments": {}}""",
            """{"type": "tool_call", "tool_name": "statistical_energy_anomalies", "arguments": {}}""",
        ]

        mock_client = MockDomoClient(tool_actions)
        # 10 model calls max
        agent = IndustrialEnergyAgent(domo_client=mock_client, max_model_calls=10)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {"status": "ok"}

            response = await agent.run("Endless queries.")

            # Hard Python gate strictly held at 5 executions
            self.assertEqual(mock_exec.call_count, 5)
            self.assertEqual(response.tool_executions_count, 5)
            self.assertTrue(response.limit_reached)

    async def test_model_call_limit_enforced_no_evidence(self):
        """Verify that agent terminates safely if model calls exceed max without resolution."""
        # Model repeatedly returns unparsable text
        invalid_outputs = ["Not JSON 1", "Not JSON 2", "Not JSON 3"]
        mock_client = MockDomoClient(invalid_outputs)
        agent = IndustrialEnergyAgent(domo_client=mock_client, max_model_calls=3, max_corrections_per_step=1)

        with self.assertRaises(AgentError):
            await agent.run("Hello?")

    async def test_tool_failure_handled_gracefully(self):
        """Tool failure is recorded in evidence and communicated to model for safe resolution."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "read_only_sql_query",
            "arguments": {"query": "SELECT * FROM non_existent_table"}
        }"""
        final = """{
            "type": "final",
            "answer": "The query could not be executed because table non_existent_table is not approved.",
            "tool_references": []
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            from app.services.agent.sql_validator import SQLValidationError
            mock_exec.side_effect = SQLValidationError("Table 'non_existent_table' is not an approved table.")

            response = await agent.run("Query my custom table.")

            self.assertEqual(mock_client.call_count, 2)
            self.assertEqual(response.tool_executions_count, 1)
            self.assertEqual(len(response.evidence), 1)

            ev = response.evidence[0]
            self.assertFalse(ev.success)
            self.assertIn("non_existent_table", ev.error)
            self.assertIn("could not be executed", response.answer)

    async def test_domo_failures_sanitized(self):
        """Domo client exceptions are sanitized to avoid credential or topology disclosure."""
        for error_cls, expected_keyword in [
            (DomoAuthenticationError("401 Unauthorized"), "authentication failed"),
            (DomoRateLimitError("429 Rate limited"), "rate limit"),
            (DomoTimeoutError("Timed out"), "timed out"),
            (DomoServerError("500 Internal Error"), "unavailable"),
        ]:
            mock_client = AsyncMock()
            mock_client.generate_text.side_effect = error_cls
            agent = IndustrialEnergyAgent(domo_client=mock_client)

            with self.assertRaises(AgentError) as ctx:
                await agent.run("Show energy metrics.")

            err_msg = str(ctx.exception).lower()
            self.assertIn(expected_keyword, err_msg)
            # Ensure no tokens or internal URLs are leaked
            self.assertNotIn("x-domo-developer-token", err_msg)
            self.assertNotIn("http://", err_msg)

    async def test_invalid_model_output_self_correction(self):
        """Model corrects its own formatting error when challenged by the system prompt."""
        # 1. Invalid syntax
        # 2. Corrected tool call
        # 3. Final answer
        responses = [
            "I will check the energy: {type: 'tool_call'}",  # Invalid prose/syntax
            """{"type": "tool_call", "tool_name": "energy_summary", "arguments": {}}""",
            """{"type": "final", "answer": "Total energy is 1,958,088 kWh.", "tool_references": ["energy_summary"]}""",
        ]

        mock_client = MockDomoClient(responses)
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {"total_consumption_kwh": 1958088.0}

            response = await agent.run("What is factory energy?")

            # 3 model calls (1 failed, 1 corrected tool call, 1 final)
            self.assertEqual(mock_client.call_count, 3)
            # Only 1 tool execution actually happened
            self.assertEqual(response.tool_executions_count, 1)
            self.assertEqual(response.tool_references, ["energy_summary"])

    async def test_unexecuted_tool_citation_rejection_and_correction(self):
        """If model cites tools it did not execute, agent forces correction or filters citation."""
        responses = [
            # 1. Calls energy_summary
            """{"type": "tool_call", "tool_name": "energy_summary", "arguments": {}}""",
            # 2. Tries to cite production_summary without executing it
            """{"type": "final", "answer": "Energy is 1M kWh, production was 10k.", "tool_references": ["energy_summary", "production_summary"]}""",
            # 3. Corrected citation
            """{"type": "final", "answer": "Energy is 1M kWh.", "tool_references": ["energy_summary"]}""",
        ]

        mock_client = MockDomoClient(responses)
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {"total_consumption_kwh": 1000000.0}

            response = await agent.run("Show energy and production.")

            self.assertEqual(response.tool_executions_count, 1)
            self.assertEqual(response.tool_references, ["energy_summary"])
            self.assertNotIn("production_summary", response.tool_references)


if __name__ == "__main__":
    unittest.main()
