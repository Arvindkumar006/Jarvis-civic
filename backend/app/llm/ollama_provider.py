"""Ollama Local Model Provider Implementation for JARVIS Civic.

Interfaces with a local Ollama daemon (e.g. http://localhost:11434).
Guaranteed zero-cost, zero-cloud, and 100% offline-compatible.
Fails gracefully without application crash if Ollama is absent or stopped.
"""

import json
import logging
from typing import Optional, Type, TypeVar
import httpx
from pydantic import BaseModel, ValidationError

from app.config.settings import settings
from app.llm.provider import LLMProvider, LLMStatus

logger = logging.getLogger("jarvis.llm.ollama")
T = TypeVar("T", bound=BaseModel)


class OllamaProvider(LLMProvider):
    """Local Ollama HTTP client implementing LLMProvider."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.JARVIS_LLM_MODEL
        self.timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS

    async def check_health(self) -> LLMStatus:
        """Probe local Ollama daemon without throwing exceptions."""
        try:
            probe_timeout = min(self.timeout, 0.5)
            async with httpx.AsyncClient(timeout=probe_timeout) as client:
                res = await client.get(f"{self.base_url}/api/version")
                if res.status_code == 200:
                    return LLMStatus.LLM_AVAILABLE
                return LLMStatus.LLM_ERROR
        except (httpx.ConnectError, httpx.TimeoutException):
            return LLMStatus.LLM_UNAVAILABLE
        except Exception as exc:
            logger.debug(f"Ollama health check error: {exc}")
            return LLMStatus.LLM_ERROR

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        """Call Ollama /api/generate for unconstrained text generation."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("response", "").strip()
                logger.warning(f"Ollama returned HTTP {res.status_code}: {res.text}")
                return ""
        except Exception as exc:
            logger.warning(f"Ollama generate_text failed: {exc}")
            return ""

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> Optional[T]:
        """Request JSON format from Ollama and validate against response_model."""
        schema_prompt = (
            f"\nYou must respond ONLY with a valid JSON object strictly matching this schema:\n"
            f"{json.dumps(response_model.model_json_schema(), indent=2)}\n"
            f"Do not include markdown fences (```json), commentary, or explanation."
        )
        combined_prompt = f"{prompt}\n{schema_prompt}"

        payload = {
            "model": self.model_name,
            "prompt": combined_prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0},
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    raw_content = res.json().get("response", "").strip()
                    if not raw_content:
                        return None
                    return response_model.model_validate_json(raw_content)
                logger.warning(f"Ollama structured error HTTP {res.status_code}: {res.text}")
                return None
        except (ValidationError, json.JSONDecodeError) as val_err:
            logger.warning(f"Failed to validate Ollama structured output against {response_model.__name__}: {val_err}")
            return None
        except Exception as exc:
            logger.warning(f"Ollama structured generation error: {exc}")
            return None
