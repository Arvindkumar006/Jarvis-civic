"""Agent 2: Civic Information Extractor.

Extracts physical geographic attributes (street, landmark, 6-digit postal PIN code)
and explicit hazard indicators strictly from citizen text.
Enforces the anti-hallucination mandate: if absent, fields evaluate to None.
"""

import re
from typing import List, Optional
from app.models.reasoning import CivicExtraction
from app.agents.prompts import CIVIC_EXTRACTOR_SYSTEM_PROMPT
from app.llm.provider import LLMProvider, LLMStatus


class CivicExtractionAgent:
    """Agent 2: Civic Information Extractor."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def extract_deterministic(self, message: str) -> CivicExtraction:
        """Deterministic extraction using exact regex for PIN code, locations, and hazards."""
        # 1. PIN code extraction: 6-digit Indian PIN code matching ^[1-9][0-9]{5}$
        pincode: Optional[str] = None
        # Look for standalone 6-digit number starting with 1-9
        pin_match = re.search(r"\b([1-9][0-9]{5})\b", message)
        if pin_match:
            pincode = pin_match.group(1)

        # 2. Hazard extraction
        hazard_flags: List[str] = []
        msg_lower = message.lower()
        if re.search(r"\b(live\s*wire|exposed\s*wire|sparking\s*wire|hanging\s*wire)\b", msg_lower):
            hazard_flags.append("Live electrical wire hazard")
        if re.search(r"\b(open\s*manhole|deep\s*hole|open\s*drain)\b", msg_lower):
            hazard_flags.append("Open manhole or pedestrian pit hazard")
        if re.search(r"\b(water\s*inside\s*house|flooding\s*home|flooding\s*hospital|flooded\s*house)\b", msg_lower):
            hazard_flags.append("Residential or hospital water ingress")
        if re.search(r"\b(ambulance|hospital\s*route|arterial\s*road)\b", msg_lower):
            hazard_flags.append("Emergency transit corridor blockage")

        # 3. Location extraction: Search for explicit location markers or prepositions
        location: Optional[str] = None
        landmark: Optional[str] = None

        # Check for landmark indicators
        landmark_match = re.search(
            r"\b(?:near|opposite|opp|behind|beside|next\s+to|in\s+front\s+of)\s+([A-Za-z0-9\s,\-\.]{3,40})(?:\.|\,|$|\bat\b|\bon\b)",
            message,
            re.IGNORECASE,
        )
        if landmark_match:
            cand = landmark_match.group(1).strip()
            # Avoid picking up full sentence if long
            if len(cand.split()) <= 6:
                landmark = cand

        # Check for location / street markers
        # Patterns like "at <Location>", "on <Road/Street>", or phrases containing Road, Nagar, Street, etc.
        loc_prep_match = re.search(
            r"\b(?:at|on|in)\s+((?:[A-Za-z0-9\s,\-]{2,40}(?:Road|Street|Nagar|Cross|Salai|Marg|Colony|Layout|Sector|Lane|Avenue|Chennai|Bangalore|Mumbai|Delhi|Hyderabad|Kolkata|Pune))[A-Za-z0-9\s,\-]*?)(?:\.|\,|$|\bnear\b|\bopposite\b|\bpincode\b)",
            message,
            re.IGNORECASE,
        )
        if loc_prep_match:
            location = loc_prep_match.group(1).strip()
        else:
            # Direct street address mention without preposition
            street_match = re.search(
                r"\b([A-Za-z0-9\s,\-]{2,30}\s+(?:Road|Street|Nagar|Cross|Salai|Marg|Colony|Layout|Sector|Lane|Avenue)(?:,\s*[A-Za-z\s]+)*)",
                message,
                re.IGNORECASE,
            )
            if street_match:
                location = street_match.group(1).strip()

        # If location is still None, but citizen provided landmark, keep location as None so missing_fields triggers
        return CivicExtraction(
            description=message.strip(),
            location=location,
            landmark=landmark,
            pincode=pincode,
            hazard_flags=hazard_flags,
        )

    async def run(self, message: str) -> CivicExtraction:
        """Run extraction using local model when healthy; otherwise deterministic fallback."""
        status = await self.provider.check_health()
        if status == LLMStatus.LLM_AVAILABLE:
            prompt = (
                f"Extract physical location, landmark, 6-digit Indian PIN code, and hazards from:\n"
                f"\"{message}\"\n"
                f"Reminder: If location or landmark is absent, return null. Never fabricate."
            )
            llm_result = await self.provider.generate_structured(
                prompt=prompt,
                response_model=CivicExtraction,
                system_prompt=CIVIC_EXTRACTOR_SYSTEM_PROMPT,
            )
            if llm_result:
                return llm_result

        return self.extract_deterministic(message)
