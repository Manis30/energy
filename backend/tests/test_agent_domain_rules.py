"""
Domain integrity and analytical rule verification tests for Industrial Energy Intelligence Agent.

Verifies adherence to the 8 core manufacturing domain principles:
1. Deterministic calculations & units (kWh, INR, kg CO2e).
2. Energy & production joins (SMT to MTR-SMT, FAL to MTR-FAL, facility utilities separate).
3. Specific Energy Consumption (SMT kWh/board vs FAL kWh/phone, Factory SEC distinction).
4. Zero-production period energy (standby/baseline load, not guaranteed waste).
5. Power factor monitoring (0.90 engineering cutoff, no unverified utility fines).
6. Production & OEE disclaimer (OEE unavailable, rework separate from rejects).
7. Anomaly detection (statistical deviations are telemetry alerts, not confirmed physical failures).
8. Timezone handling (timezone-naive timestamps without IST/UTC conversion).
"""

import unittest
from unittest.mock import patch

from app.services.agent.agent import IndustrialEnergyAgent
from app.services.agent.prompts import get_system_prompt
from backend.tests.test_agent_orchestration import MockDomoClient


class TestAgentDomainRules(unittest.IsolatedAsyncioTestCase):
    """Test suite ensuring agent prompt and execution adhere to domain constraints."""

    def test_system_prompt_domain_rules_present(self):
        """Verify all 8 mandatory domain rules are explicitly present in the system prompt."""
        prompt = get_system_prompt()

        # Rule 1: Deterministic Calculations & Evidence
        self.assertIn("All numerical totals, costs, emissions, quantities, and rates MUST come directly from executed tool outputs", prompt)
        self.assertIn("NEVER invent, extrapolate, or hallucinate metrics", prompt)

        # Rule 2: Energy & Production Joins
        self.assertIn("NEVER join energy and production facts on timestamp and plant alone", prompt)
        self.assertIn("SMT production lines map strictly to meter 'MTR-SMT'", prompt)
        self.assertIn("FAL production lines map strictly to meter 'MTR-FAL'", prompt)
        self.assertIn("NEVER arbitrarily allocate facility utilities to specific lines or products", prompt)

        # Rule 3: Specific Energy Consumption
        self.assertIn("SMT Process SEC is measured in kWh per board", prompt)
        self.assertIn("FAL Process SEC is measured in kWh per phone", prompt)
        self.assertIn("Factory SEC = Total Plant Energy (all meters) / FAL Finished Output (phones)", prompt)
        self.assertIn("Product Process SEC accounts only for direct process lines (SMT + FAL) and strictly excludes facility utilities", prompt)

        # Rule 4: Zero-Production Period Energy
        self.assertIn("Energy consumed during zero-production hours is baseline/standby load", prompt)
        self.assertIn("It is NOT automatically waste or guaranteed recoverable savings", prompt)

        # Rule 5: Power Factor
        self.assertIn("0.90 is an internal engineering monitoring threshold", prompt)
        self.assertIn("Do NOT assert statutory regulatory non-compliance or grid penalty fines", prompt)

        # Rule 6: Production & OEE
        self.assertIn("OEE (Overall Equipment Effectiveness) is UNAVAILABLE from the current source data", prompt)
        self.assertIn("Keep rework units separate from rejected scrap units", prompt)

        # Rule 7: Anomaly Detection
        self.assertIn("Statistical z-score deviations or rolling baseline excursions are telemetry alerts, NOT confirmed physical equipment breakdowns", prompt)

        # Rule 8: Timezone & Dates
        self.assertIn("Source timestamps are timezone-naive", prompt)
        self.assertIn("NEVER assume Indian Standard Time (IST) or UTC conversions", prompt)

    async def test_energy_summary_preserves_units_and_tool(self):
        """Verify energy question invokes energy_summary and cites evidence."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "energy_summary",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        final = """{
            "type": "final",
            "answer": "Plant IN-TN-01 consumed 1,180,450.25 kWh with an electricity cost of INR 9,738,714.50 and CO2e emissions of 967,969.21 kg.",
            "tool_references": ["energy_summary"]
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {
                "total_consumption_kwh": 1180450.25,
                "total_cost_inr": 9738714.50,
                "total_co2e_kg": 967969.21,
            }

            response = await agent.run("What was the energy consumption and carbon emissions for IN-TN-01?")

            self.assertEqual(response.tool_references, ["energy_summary"])
            self.assertIn("kWh", response.answer)
            self.assertIn("INR", response.answer)
            self.assertIn("kg", response.answer)

    async def test_production_summary_distinguishes_rework_and_rejects(self):
        """Verify production question invokes production_summary and keeps rework separate from rejects."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "production_summary",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        final = """{
            "type": "final",
            "answer": "Production Summary: Target: 250,000 units, Actual: 245,000 units, Good: 238,000 units, Rejects: 4,000 units, Rework: 3,000 units. Rework units are repaired while rejects are scrapped.",
            "tool_references": ["production_summary"]
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {
                "target_quantity": 250000,
                "actual_quantity": 245000,
                "good_quantity": 238000,
                "reject_quantity": 4000,
                "rework_quantity": 3000,
            }

            response = await agent.run("Show production output and scrap numbers.")

            self.assertEqual(response.tool_references, ["production_summary"])
            self.assertIn("Rejects", response.answer)
            self.assertIn("Rework", response.answer)

    async def test_oee_unavailability_handled_without_hallucination(self):
        """Verify OEE question produces clear unavailability explanation without fabricating KPIs."""
        final = """{
            "type": "final",
            "answer": "OEE (Overall Equipment Effectiveness) is unavailable from the current telemetry dataset because planned operating times, micro-stoppages, and ideal cycle times are not recorded.",
            "tool_references": []
        }"""

        mock_client = MockDomoClient([final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        response = await agent.run("Calculate OEE for SMT-L1.")
        self.assertEqual(response.tool_executions_count, 0)
        self.assertIn("unavailable", response.answer.lower())

    async def test_process_sec_distinguishes_smt_and_fal_units(self):
        """Verify process SEC answers preserve kWh/board for SMT and kWh/phone for FAL."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "process_energy_intensity",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        final = """{
            "type": "final",
            "answer": "Process SEC results: SMT process SEC is 0.45 kWh/board (intermediate PCB) and FAL process SEC is 1.12 kWh/phone (finished device). These output units are distinct and cannot be summed.",
            "tool_references": ["process_energy_intensity"]
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {
                "smt_sec_kwh_per_board": 0.45,
                "fal_sec_kwh_per_phone": 1.12,
            }

            response = await agent.run("What are the process SEC numbers?")
            self.assertEqual(response.tool_references, ["process_energy_intensity"])
            self.assertIn("kWh/board", response.answer)
            self.assertIn("kWh/phone", response.answer)

    async def test_factory_sec_vs_process_sec(self):
        """Verify factory SEC tool usage and segregation of facility utilities."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "factory_energy_intensity",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        final = """{
            "type": "final",
            "answer": "Factory SEC is 5.20 kWh/phone (Total plant kWh across all 5 meters divided by finished FAL phones). Direct process accounts for 1.57 kWh/phone, while facility utilities (HVAC, Chiller, Compressor) account for 3.63 kWh/phone.",
            "tool_references": ["factory_energy_intensity"]
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {
                "factory_sec": 5.20,
                "process_sec": 1.57,
                "utility_sec": 3.63,
            }

            response = await agent.run("What is the Factory SEC for IN-TN-01?")
            self.assertEqual(response.tool_references, ["factory_energy_intensity"])
            self.assertIn("Factory SEC", response.answer)
            self.assertIn("HVAC, Chiller, Compressor", response.answer)

    async def test_zero_production_energy_does_not_claim_guaranteed_savings(self):
        """Verify zero-production energy is framed as standby baseline load, not guaranteed waste."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "zero_production_period_energy",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        final = """{
            "type": "final",
            "answer": "During zero-production downtime periods, process lines consumed 12,450 kWh. This represents baseline standby and idle consumption, not guaranteed avoidable waste or savings.",
            "tool_references": ["zero_production_period_energy"]
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {
                "total_standby_kwh": 12450.0,
            }

            response = await agent.run("How much energy was wasted during line stoppages?")
            self.assertEqual(response.tool_references, ["zero_production_period_energy"])
            self.assertIn("standby", response.answer.lower())

    async def test_power_factor_monitoring_not_statutory_penalty(self):
        """Verify power factor readings below 0.90 are framed as engineering thresholds without legal penalty claims."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "low_power_factor_anomalies",
            "arguments": {"plant_id": "IN-TN-01"}
        }"""
        final = """{
            "type": "final",
            "answer": "Detected 14 readings where power factor fell below the configured 0.90 technical benchmark. Note: Commercial electricity tariff billing penalties require contract verification.",
            "tool_references": ["low_power_factor_anomalies"]
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {"anomaly_count": 14}

            response = await agent.run("Did we violate power factor regulations?")
            self.assertEqual(response.tool_references, ["low_power_factor_anomalies"])
            self.assertIn("0.90", response.answer)

    async def test_statistical_anomalies_framed_as_telemetry_alerts(self):
        """Verify anomalies are explained as statistical excursions, not confirmed physical breakdowns."""
        tool_call = """{
            "type": "tool_call",
            "tool_name": "statistical_energy_anomalies",
            "arguments": {"meter_id": "MTR-HVAC"}
        }"""
        final = """{
            "type": "final",
            "answer": "Found 3 statistical Z-score anomalies on MTR-HVAC. These are telemetry alerts indicating deviation from the meter baseline, not confirmed equipment faults.",
            "tool_references": ["statistical_energy_anomalies"]
        }"""

        mock_client = MockDomoClient([tool_call, final])
        agent = IndustrialEnergyAgent(domo_client=mock_client)

        with patch("app.services.agent.agent.execute_tool") as mock_exec:
            mock_exec.return_value = {"anomalies_detected": 3}

            response = await agent.run("Did HVAC break down?")
            self.assertEqual(response.tool_references, ["statistical_energy_anomalies"])
            self.assertIn("telemetry alert", response.answer.lower())


if __name__ == "__main__":
    unittest.main()
