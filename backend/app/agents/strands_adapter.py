"""AWS Strands Adapter and Custom Tools for JARVIS Civic.

Integrates AWS Strands Agents SDK with the local inference provider (Ollama)
and provides registered Strands tools for civic validation, routing, and scoring.
"""

from typing import Any, AsyncGenerator, AsyncIterable, Dict, List, Optional, Type, TypeVar
import re
import threading
from pydantic import BaseModel

from strands import tool
from strands.models.model import Model
from strands.types.content import Messages, SystemContentBlock
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec

from app.models.enums import CivicIntent, ControlledDepartment, UrgencyLevel
from app.llm.provider import LLMProvider

T = TypeVar("T", bound=BaseModel)

# Controlled mapping table
DEPARTMENT_ROUTING_MAP = {
    CivicIntent.WATERLOGGING.value: ControlledDepartment.DRAINAGE_STORMWATER.value,
    CivicIntent.DRAINAGE_BLOCKAGE.value: ControlledDepartment.DRAINAGE_STORMWATER.value,
    CivicIntent.ROAD_POTHOLE.value: ControlledDepartment.PWD_ROADS.value,
    CivicIntent.STREETLIGHT_OUTAGE.value: ControlledDepartment.MUNICIPAL_CORPORATION.value,
    CivicIntent.GARBAGE_ACCUMULATION.value: ControlledDepartment.WASTE_MANAGEMENT.value,
    CivicIntent.WATER_SUPPLY_ISSUE.value: ControlledDepartment.WATER_SUPPLY.value,
    CivicIntent.ELECTRICITY_OUTAGE.value: ControlledDepartment.ELECTRICITY_UTILITY.value,
    CivicIntent.PUBLIC_INFRASTRUCTURE_DAMAGE.value: ControlledDepartment.MUNICIPAL_CORPORATION.value,
    CivicIntent.OTHER_CIVIC_ISSUE.value: ControlledDepartment.OTHER_MANUAL_REVIEW.value,
}


@tool
def validate_pincode_tool(pincode: str) -> bool:
    """Validate whether an Indian postal PIN code matches '^[1-9][0-9]{5}$'."""
    if not isinstance(pincode, str):
        return False
    return bool(re.match(r"^[1-9][0-9]{5}$", pincode.strip()))


@tool
def map_department_tool(intent: str) -> str:
    """Map a recognized civic intent to the recommended municipal department."""
    return DEPARTMENT_ROUTING_MAP.get(intent, ControlledDepartment.OTHER_MANUAL_REVIEW.value)


@tool
def calculate_urgency_tool(intent: str, hazard_flags: List[str]) -> Dict[str, str]:
    """Calculate objective civic urgency score and concise rationale."""
    score = 0
    rationales: List[str] = []

    # Intent baseline score
    if intent in [CivicIntent.ELECTRICITY_OUTAGE.value, CivicIntent.PUBLIC_INFRASTRUCTURE_DAMAGE.value]:
        score += 3
        rationales.append("Significant public disruption risk")
    elif intent in [CivicIntent.WATERLOGGING.value, CivicIntent.ROAD_POTHOLE.value]:
        score += 2
        rationales.append("Pedestrian and vehicular transit disruption")
    else:
        score += 1

    # Hazard indicator factors
    for flag in hazard_flags:
        f_lower = flag.lower()
        if ("live" in f_lower and "wire" in f_lower) or "exposed" in f_lower or "open manhole" in f_lower or "deep ditch" in f_lower:
            score += 4
            rationales.append("Acute public safety hazard reported")
        elif ("water" in f_lower and ("house" in f_lower or "home" in f_lower or "hospital" in f_lower)) or "flooding" in f_lower:
            score += 3
            rationales.append("Direct structural or residential ingress reported")
        elif "ambulance" in f_lower or "arterial" in f_lower or "blocked" in f_lower:
            score += 3
            rationales.append("Critical transit corridor obstruction")
        elif "sewage" in f_lower or "drinking water" in f_lower:
            score += 2
            rationales.append("Severe contamination risk")

    if score >= 5:
        level = UrgencyLevel.CRITICAL.value
    elif score >= 3:
        level = UrgencyLevel.HIGH.value
    elif score >= 2:
        level = UrgencyLevel.MEDIUM.value
    else:
        level = UrgencyLevel.LOW.value

    rationale_str = "; ".join(rationales) if rationales else "Standard community defect severity."
    return {"urgency": level, "rationale": rationale_str}


@tool
def detect_missing_fields_tool(location: Optional[str]) -> List[str]:
    """Detect mandatory fields missing from intake (location is strictly required)."""
    missing = []
    if not location or not location.strip():
        missing.append("location")
    return missing


class LocalStrandsModel(Model):
    """Custom Strands Model adapter that binds to our local LLMProvider.

    Allows AWS Strands Agent instances to run locally through Ollama or fallback.
    """

    def __init__(self, provider: LLMProvider, model_name: str = "local-ollama"):
        self.provider = provider
        self.model_name = model_name
        self.config: Dict[str, Any] = {"model": model_name}

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> Any:
        return self.config

    async def structured_output(
        self,
        output_model: Type[T],
        prompt: Messages,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, T | Any], None]:
        """Generate structured Pydantic output using the local provider."""
        # Convert prompt messages to a single string for local model
        text_prompt = "\n".join(
            str(m.content if hasattr(m, "content") else m) for m in (prompt if isinstance(prompt, list) else [prompt])
        )
        result = await self.provider.generate_structured(
            prompt=text_prompt,
            response_model=output_model,
            system_prompt=system_prompt,
        )
        yield {"structured_output": result}

    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[List[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: Optional[ToolChoice] = None,
        system_prompt_content: Optional[List[SystemContentBlock]] = None,
        invocation_state: Optional[Dict[str, Any]] = None,
        cancel_signal: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        """Stream chunks from local model (minimal yield for compliance)."""
        prompt_text = "\n".join(str(m) for m in (messages if isinstance(messages, list) else [messages]))
        text = await self.provider.generate_text(prompt=prompt_text, system_prompt=system_prompt)
        # Yield as string representation
        yield text  # type: ignore
