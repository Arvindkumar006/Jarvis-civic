"""Tests for Local LLM Provider Abstraction and Health Checking."""

import pytest
from app.llm.provider import LLMProvider, LLMStatus
from app.llm.ollama_provider import OllamaProvider
from app.models.reasoning import IntentAnalysis
from app.models.enums import CivicIntent


class MockWorkingLLMProvider(LLMProvider):
    """Test double simulating an active local LLM."""

    async def check_health(self) -> LLMStatus:
        return LLMStatus.LLM_AVAILABLE

    async def generate_text(self, prompt: str, system_prompt=None, temperature=0.1) -> str:
        return "Where is the problem located?"

    async def generate_structured(self, prompt: str, response_model, system_prompt=None):
        if response_model == IntentAnalysis:
            return IntentAnalysis(
                intent=CivicIntent.ROAD_POTHOLE,
                is_civic=True,
                language="English",
                confidence=0.92,
                initial_description="Large pothole on the road",
            )
        return None


@pytest.mark.asyncio
async def test_ollama_graceful_offline_health():
    """Verify OllamaProvider reports LLM_UNAVAILABLE when server is unreachable without crashing."""
    provider = OllamaProvider(base_url="http://127.0.0.1:59999", timeout=0.5)
    status = await provider.check_health()
    assert status == LLMStatus.LLM_UNAVAILABLE


@pytest.mark.asyncio
async def test_ollama_generate_text_fallback_on_unreachable():
    """Verify generate_text returns empty string on failure rather than raising uncaught exceptions."""
    provider = OllamaProvider(base_url="http://127.0.0.1:59999", timeout=0.5)
    result = await provider.generate_text("Hello")
    assert result == ""


@pytest.mark.asyncio
async def test_mock_llm_provider():
    """Verify provider abstraction contract works with mock double."""
    mock_provider = MockWorkingLLMProvider()
    status = await mock_provider.check_health()
    assert status == LLMStatus.LLM_AVAILABLE

    structured = await mock_provider.generate_structured("Fix road", IntentAnalysis)
    assert structured is not None
    assert structured.intent == CivicIntent.ROAD_POTHOLE
    assert structured.confidence == 0.92
