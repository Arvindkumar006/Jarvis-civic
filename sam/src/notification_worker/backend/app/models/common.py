"""Common Models, Validators, and Utilities for JARVIS Civic."""

import re
import secrets
from typing import Optional
from pydantic import BaseModel, Field

from app.models.civic_state import CanonicalCivicState

# Case ID Regex Pattern: NS-<CITY_CODE (3-4 uppercase letters)>-<YEAR (4 digits)>-<4 uppercase hex chars>
CASE_ID_PATTERN = r"^NS-[A-Z]{3,4}-\d{4}-[A-F0-9]{4}$"


def validate_case_id(case_id: str) -> bool:
    """Validate whether a given case ID matches the standard JARVIS Civic format."""
    if not isinstance(case_id, str):
        return False
    return bool(re.match(CASE_ID_PATTERN, case_id))


def generate_case_id(city_code: str = "CHN", year: int = 2026) -> str:
    """Generate a valid Case ID adhering to the canonical format: NS-<CITY>-<YEAR>-<4_HEX>.

    Example: NS-CHN-2026-9E4B
    """
    clean_city = city_code.strip().upper()
    if not re.match(r"^[A-Z]{3,4}$", clean_city):
        clean_city = "CIV"
    random_hex = secrets.token_hex(2).upper()
    return f"NS-{clean_city}-{year}-{random_hex}"


class ConversationRequest(BaseModel):
    """Citizen conversation intake request payload."""

    session_id: str = Field(..., description="Unique session tracking identifier")
    message: str = Field(..., min_length=1, description="Citizen problem statement or voice transcript")
    language: Optional[str] = Field(default="en", description="Language hint or detected dialect")
    previous_state: Optional[CanonicalCivicState] = Field(default=None, description="Previous conversation canonical state context")
    missing_fields: Optional[list[str]] = Field(default=None, description="Prior unresolved fields needing clarification")



class ConversationResponse(BaseModel):
    """Citizen conversation response containing updated extraction state."""

    session_id: str = Field(..., description="Active session tracking identifier")
    state: CanonicalCivicState = Field(..., description="Current canonical civic extraction state")
    reply: Optional[str] = Field(default=None, description="Conversational feedback or follow-up reply")
