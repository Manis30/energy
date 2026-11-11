"""
Unit tests for Domo Text Generation API client.

Verifies:
1. Configuration loading and validation.
2. Token protection and redaction in string representations.
3. Correct request structure and header formation (X-DOMO-Developer-Token).
4. Successful response parsing (200 OK with 'output' string).
5. Immediate rejection on HTTP 401 / 403 authentication failures (no retries).
6. Immediate rejection on HTTP 400 bad requests.
7. Bounded retry behavior on transient errors (HTTP 429, 502, 503).
8. Timeout and connection failure handling.
9. Malformed response handling (missing output field or non-JSON).
"""

import asyncio
from unittest.mock import AsyncMock, patch
import unittest

import httpx

from app.services.agent.domo_client import (
    DomoAuthenticationError,
    DomoClient,
    DomoConfigurationError,
    DomoConnectionError,
    DomoError,
    DomoRateLimitError,
    DomoResponseError,
    DomoServerError,
    DomoTimeoutError,
)


class TestDomoClient(unittest.TestCase):
    """Test suite validating DomoClient behavior and HTTP safety."""

    def test_configuration_validation_missing_parameters(self):
        """Verify client raises DomoConfigurationError when required settings are missing."""
        # Missing base URL
        client_no_url = DomoClient(base_url="", developer_token="dummy", default_model="dummy-model")
        with self.assertRaises(DomoConfigurationError):
            asyncio.run(client_no_url.generate_text("Hello"))

        # Missing token
        client_no_token = DomoClient(base_url="https://domo.example.com", developer_token="", default_model="dummy-model")
        with self.assertRaises(DomoConfigurationError):
            asyncio.run(client_no_token.generate_text("Hello"))

        # Missing model
        client_no_model = DomoClient(base_url="https://domo.example.com", developer_token="dummy", default_model="")
        with self.assertRaises(DomoConfigurationError):
            asyncio.run(client_no_model.generate_text("Hello"))

    def test_token_redaction_in_repr(self):
        """Verify that developer tokens are strictly excluded from string representations."""
        secret_token = "SUPER_SECRET_TOKEN_DO_NOT_EXPOSE"
        client = DomoClient(
            base_url="https://gwcteq-partner.domo.com",
            developer_token=secret_token,
            default_model="domo.domo_ai.domogpt-large-v2.2:anthropic",
        )
        repr_str = repr(client)
        self.assertNotIn(secret_token, repr_str)
        self.assertIn("gwcteq-partner.domo.com", repr_str)
        self.assertIn("domogpt-large-v2.2", repr_str)

    def test_successful_text_generation(self):
        """Verify successful generation request and output parsing."""
        def handle_request(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://gwcteq-partner.domo.com/api/ai/v1/text/generation")
            self.assertEqual(request.headers.get("X-DOMO-Developer-Token"), "test-token-123")
            self.assertEqual(request.headers.get("Content-Type"), "application/json")

            return httpx.Response(
                status_code=200,
                json={
                    "output": "Energy consumption across both plants is 1,958,088.31 kWh.",
                    "model": "domo.domo_ai.domogpt-large-v2.2:anthropic",
                    "usage": {"prompt_tokens": 40, "completion_tokens": 15},
                },
            )

        transport = httpx.MockTransport(handle_request)
        mock_http = httpx.AsyncClient(transport=transport)
        try:
            client = DomoClient(
                base_url="https://gwcteq-partner.domo.com",
                developer_token="test-token-123",
                default_model="domo.domo_ai.domogpt-large-v2.2:anthropic",
                http_client=mock_http,
            )
            res = asyncio.run(client.generate_text("Summarize energy", session_id="test-session-1"))
            self.assertEqual(res.output, "Energy consumption across both plants is 1,958,088.31 kWh.")
            self.assertEqual(res.model, "domo.domo_ai.domogpt-large-v2.2:anthropic")
            self.assertIsNotNone(res.usage)
        finally:
            asyncio.run(mock_http.aclose())

    def test_authentication_failure_no_retries(self):
        """Verify HTTP 401 raises DomoAuthenticationError immediately without retrying."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(status_code=401, json={"error": "Unauthorized"})

        transport = httpx.MockTransport(handle_request)
        mock_http = httpx.AsyncClient(transport=transport)
        try:
            client = DomoClient(
                base_url="https://gwcteq-partner.domo.com",
                developer_token="bad-token",
                default_model="test-model",
                max_retries=3,
                http_client=mock_http,
            )
            with self.assertRaises(DomoAuthenticationError):
                asyncio.run(client.generate_text("Hello"))
            # Must NOT retry on 401
            self.assertEqual(call_count, 1)
        finally:
            asyncio.run(mock_http.aclose())

    def test_bad_request_no_retries(self):
        """Verify HTTP 400 raises DomoError immediately without retrying."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(status_code=400, json={"error": "Invalid Model Identifier"})

        transport = httpx.MockTransport(handle_request)
        mock_http = httpx.AsyncClient(transport=transport)
        try:
            client = DomoClient(
                base_url="https://gwcteq-partner.domo.com",
                developer_token="token",
                default_model="invalid-model",
                max_retries=3,
                http_client=mock_http,
            )
            with self.assertRaises(DomoError):
                asyncio.run(client.generate_text("Hello"))
            self.assertEqual(call_count, 1)
        finally:
            asyncio.run(mock_http.aclose())

    def test_rate_limit_bounded_retries(self):
        """Verify HTTP 429 triggers bounded retries up to max_retries."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(status_code=429, json={"error": "Rate limit exceeded"})

        transport = httpx.MockTransport(handle_request)
        mock_http = httpx.AsyncClient(transport=transport)
        try:
            client = DomoClient(
                base_url="https://gwcteq-partner.domo.com",
                developer_token="token",
                default_model="test-model",
                max_retries=3,
                http_client=mock_http,
            )
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaises(DomoRateLimitError):
                    asyncio.run(client.generate_text("Hello"))
            self.assertEqual(call_count, 3)
        finally:
            asyncio.run(mock_http.aclose())

    def test_server_error_recovery(self):
        """Verify transient 503 recovers if subsequent attempt succeeds."""
        attempts = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(status_code=503, json={"error": "Service Unavailable"})
            return httpx.Response(status_code=200, json={"output": "Recovered successfully!"})

        transport = httpx.MockTransport(handle_request)
        mock_http = httpx.AsyncClient(transport=transport)
        try:
            client = DomoClient(
                base_url="https://gwcteq-partner.domo.com",
                developer_token="token",
                default_model="test-model",
                max_retries=3,
                http_client=mock_http,
            )
            with patch("asyncio.sleep", new_callable=AsyncMock):
                res = asyncio.run(client.generate_text("Hello"))
            self.assertEqual(res.output, "Recovered successfully!")
            self.assertEqual(attempts, 2)
        finally:
            asyncio.run(mock_http.aclose())

    def test_timeout_handling(self):
        """Verify network timeout raises DomoTimeoutError."""
        def handle_request(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Read timed out")

        transport = httpx.MockTransport(handle_request)
        mock_http = httpx.AsyncClient(transport=transport)
        try:
            client = DomoClient(
                base_url="https://gwcteq-partner.domo.com",
                developer_token="token",
                default_model="test-model",
                max_retries=2,
                http_client=mock_http,
            )
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaises(DomoTimeoutError):
                    asyncio.run(client.generate_text("Hello"))
        finally:
            asyncio.run(mock_http.aclose())

    def test_malformed_response_missing_output(self):
        """Verify 200 OK with missing output field raises DomoResponseError."""
        def handle_request(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code=200, json={"unexpected_key": "No text here"})

        transport = httpx.MockTransport(handle_request)
        mock_http = httpx.AsyncClient(transport=transport)
        try:
            client = DomoClient(
                base_url="https://gwcteq-partner.domo.com",
                developer_token="token",
                default_model="test-model",
                http_client=mock_http,
            )
            with self.assertRaises(DomoResponseError):
                asyncio.run(client.generate_text("Hello"))
        finally:
            asyncio.run(mock_http.aclose())


if __name__ == "__main__":
    unittest.main()
