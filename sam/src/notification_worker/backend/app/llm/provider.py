"""LLM Provider Abstraction Layer for JARVIS Civic.

Enforces zero-billing, local-only execution. Decouples agents from concrete inference engines.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMStatus(str, Enum):
    """Operational availability status of the local LLM inference engine."""

    LLM_AVAILABLE = "LLM_AVAILABLE"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_ERROR = "LLM_ERROR"


class LLMProvider(ABC):
    """Abstract interface for local LLM inference providers."""

    @abstractmethod
    async def check_health(self) -> LLMStatus:
        """Check whether the local inference provider is running and reachable."""
        pass

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        """Generate raw text response from the local model."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> Optional[T]:
        """Generate structured output validated against a Pydantic model."""
        pass
