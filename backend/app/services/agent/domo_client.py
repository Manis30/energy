"""
Domo Text Generation API Client.

Provides a secure, asynchronous HTTP client for Domo AI Services Text Generation API.
Features:
- Token-authenticated requests via X-DOMO-Developer-Token header.
- Bounded retries for transient HTTP errors (502, 503, 504, 429) and network timeouts.
- Strict rejection of retries on 401/403 (auth) and 400/422 (client error).
- Zero credential logging or exposure.
- Clean AsyncClient lifecycle management.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DomoError(Exception):
    """Base exception for all Domo client errors."""
    pass


class DomoConfigurationError(DomoError):
    """Raised when required Domo configuration parameters are missing or invalid."""
    pass


class DomoAuthenticationError(DomoError):
    """Raised when authentication with Domo fails (HTTP 401 / 403)."""
    pass


class DomoRateLimitError(DomoError):
    """Raised when Domo API rate limits are exceeded (HTTP 429)."""
    pass


class DomoServerError(DomoError):
    """Raised when Domo returns a 5xx server error."""
    pass


class DomoTimeoutError(DomoError):
    """Raised when request to Domo API times out."""
    pass


class DomoConnectionError(DomoError):
    """Raised when network connection to Domo API cannot be established."""
    pass


class DomoResponseError(DomoError):
    """Raised when Domo API returns an unexpected or malformed response payload."""
    pass


# ---------------------------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------------------------

class DomoTextGenerationRequest(BaseModel):
    """Payload sent to Domo Text Generation endpoint."""
    model: str = Field(..., description="Target model identifier")
    input: str = Field(..., description="Prompt or instructions string")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0, description="Sampling temperature")
    session_id: Optional[str] = Field(None, description="Optional session or conversation ID for context tracking")


class DomoTextGenerationResponse(BaseModel):
    """Structured response parsed from Domo Text Generation output."""
    output: str = Field(..., description="Generated text response from the model")
    model: str = Field(..., description="Model identifier used for generation")
    usage: Optional[Dict[str, Any]] = Field(default=None, description="Token usage statistics if provided")
    raw: Optional[Dict[str, Any]] = Field(default=None, description="Sanitized raw payload from Domo API")


# ---------------------------------------------------------------------------
# Client Implementation
# ---------------------------------------------------------------------------

class DomoClient:
    """
    Asynchronous client for interacting with Domo Text Generation API.
    Handles token authentication, bounded retries, and response parsing.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        developer_token: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url if base_url is not None else (settings.DOMO_BASE_URL or "")).rstrip("/")
        self._token = developer_token if developer_token is not None else (settings.DOMO_DEVELOPER_TOKEN or "")
        self.default_model = default_model if default_model is not None else (settings.MODEL_NAME or "")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.DOMO_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else settings.DOMO_MAX_RETRIES

        self._external_client = http_client is not None
        self._client: Optional[httpx.AsyncClient] = http_client

    def _get_client(self) -> httpx.AsyncClient:
        """Get or initialize the underlying httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client if internally managed."""
        if self._client is not None and not self._client.is_closed and not self._external_client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "DomoClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def _validate_configuration(self) -> None:
        """Validate that all mandatory settings are present before making calls."""
        if not self.base_url:
            raise DomoConfigurationError("DOMO_BASE_URL is not configured.")
        if not self._token:
            raise DomoConfigurationError("DOMO_DEVELOPER_TOKEN is not configured.")
        if not self.default_model:
            raise DomoConfigurationError("MODEL_NAME is not configured.")

    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.0,
        session_id: Optional[str] = None,
    ) -> DomoTextGenerationResponse:
        """
        Execute a text generation call to Domo AI Services.

        Args:
            prompt: User or system prompt input string.
            model: Optional model override (defaults to configured MODEL_NAME).
            temperature: Sampling temperature (default 0.0 for deterministic answers).
            session_id: Optional conversation/session ID.

        Returns:
            DomoTextGenerationResponse containing model output.
        """
        self._validate_configuration()

        target_model = model or self.default_model
        endpoint = f"{self.base_url}/api/ai/v1/text/generation"

        # Request headers — token is never logged or exposed
        headers = {
            "X-DOMO-Developer-Token": self._token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Request payload conforming to Domo text generation contract
        payload: Dict[str, Any] = {
            "model": target_model,
            "input": prompt,
            "temperature": temperature,
        }
        if session_id:
            payload["sessionId"] = session_id

        client = self._get_client()

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                )

                # 1. Authentication failures (401 / 403) — never retry
                if response.status_code in (401, 403):
                    raise DomoAuthenticationError(
                        f"Domo authentication failed with HTTP {response.status_code}. "
                        "Please verify DOMO_DEVELOPER_TOKEN."
                    )

                # 2. Client error / Bad Request (400 / 422) — never retry
                if response.status_code in (400, 422):
                    raise DomoError(
                        f"Domo API rejected request with HTTP {response.status_code}: invalid model or payload structure."
                    )

                # 3. Rate limiting (429) — retry if attempts remain
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        backoff = 0.5 * (2 ** (attempt - 1))
                        logger.warning("Domo rate limit (429) encountered. Backing off for %.2fs...", backoff)
                        await asyncio.sleep(backoff)
                        continue
                    raise DomoRateLimitError("Domo API rate limit exceeded after maximum retry attempts.")

                # 4. Server errors (5xx) — retry if attempts remain
                if response.status_code >= 500:
                    if attempt < self.max_retries:
                        backoff = 0.5 * (2 ** (attempt - 1))
                        logger.warning("Domo server error (%d). Retrying in %.2fs...", response.status_code, backoff)
                        await asyncio.sleep(backoff)
                        continue
                    raise DomoServerError(f"Domo server returned error HTTP {response.status_code} after retries.")

                # 5. Success (200 OK)
                if response.status_code == 200:
                    return self._parse_success_response(response, target_model)

                # Fallback unexpected status
                raise DomoError(f"Unexpected response status from Domo API: HTTP {response.status_code}")

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                last_error = DomoTimeoutError(f"Request to Domo API timed out after {self.timeout_seconds}s.")
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    logger.warning("Domo request timeout. Retrying in %.2fs...", backoff)
                    await asyncio.sleep(backoff)
                    continue
                raise last_error from e

            except (httpx.ConnectError, httpx.NetworkError) as e:
                last_error = DomoConnectionError("Failed to connect to Domo AI API service.")
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    logger.warning("Domo connection error. Retrying in %.2fs...", backoff)
                    await asyncio.sleep(backoff)
                    continue
                raise last_error from e

        # If loop exits without returning or raising
        if last_error:
            raise last_error
        raise DomoError("Domo request failed after maximum retry attempts.")

    def _parse_success_response(self, response: httpx.Response, model_name: str) -> DomoTextGenerationResponse:
        """Parse and validate JSON payload from Domo 200 OK response."""
        try:
            data = response.json()
        except Exception as e:
            raise DomoResponseError("Domo API returned an invalid non-JSON response payload.") from e

        if not isinstance(data, dict):
            raise DomoResponseError("Domo API response payload is not a JSON object.")

        # Extract output text from standard Domo output field
        output_text = None
        if "output" in data and isinstance(data["output"], str):
            output_text = data["output"]
        elif "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
            choice = data["choices"][0]
            if isinstance(choice, dict):
                output_text = choice.get("message", {}).get("content") or choice.get("text")
        elif "text" in data and isinstance(data["text"], str):
            output_text = data["text"]

        if output_text is None:
            raise DomoResponseError("Domo API response missing 'output' text field in payload.")

        return DomoTextGenerationResponse(
            output=output_text,
            model=data.get("model", model_name),
            usage=data.get("usage"),
            raw=data,
        )

    def __repr__(self) -> str:
        # Safe string representation: token is strictly omitted
        return f"<DomoClient base_url={self.base_url!r} default_model={self.default_model!r}>"


# ---------------------------------------------------------------------------
# Module-level client lifecycle singleton
# ---------------------------------------------------------------------------

_global_domo_client: Optional[DomoClient] = None


def get_domo_client() -> DomoClient:
    """Get or instantiate global reusable DomoClient instance."""
    global _global_domo_client
    if _global_domo_client is None:
        _global_domo_client = DomoClient()
    return _global_domo_client


async def close_domo_client() -> None:
    """Gracefully close the global DomoClient connection pool."""
    global _global_domo_client
    if _global_domo_client is not None:
        await _global_domo_client.close()
        _global_domo_client = None
