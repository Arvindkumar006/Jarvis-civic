"""Agent 1: Requirement & Intent Analyzer.

Dissects multi-sentence citizen utterances, identifies the core civic defect
from the controlled taxonomy, classifies the natural language, and assesses basic confidence.
Uses AWS Strands Agent wrapper with local LLM and deterministic fallback.
"""

import re
from typing import Optional
from app.models.enums import CivicIntent
from app.models.reasoning import IntentAnalysis
from app.agents.prompts import INTENT_ANALYZER_SYSTEM_PROMPT
from app.llm.provider import LLMProvider, LLMStatus

# Deterministic pattern matching keywords
INTENT_KEYWORD_PATTERNS = [
    (
        CivicIntent.WATERLOGGING,
        [
            r"waterlog",
            r"water\s*log",
            r"flooded\s+road",
            r"water\s+on\s+road",
            r"rain\s*water\s+accumulat",
            r"water\s+standing",
            r"stagnant\s+water",
            r"தண்ணீர்[\s\S]*தேங்",
            r"தேங்கி",
            r"தண்ணீர்\s*தேக்கம்",
            r"पानी\s*भर",
            r"जलभराव",
        ],
    ),
    (
        CivicIntent.DRAINAGE_BLOCKAGE,
        [
            r"drain\s*blocked",
            r"drainage\s*blocked",
            r"blocked\s+drain",
            r"sewage\s*overflow",
            r"clogged\s+drain",
            r"gutter",
            r"நாலா",
            r"கழிவுநீர்",
        ],
    ),
    (
        CivicIntent.ROAD_POTHOLE,
        [
            r"pothole",
            r"road\s*hole",
            r"broken\s+road",
            r"damaged\s+road",
            r"crater",
            r"ரோடு\s*பள்ளம்",
            r"सड़क\s*खराब",
            r"गड्ढा",
            r"गड्ढे",
        ],
    ),
    (
        CivicIntent.STREETLIGHT_OUTAGE,
        [
            r"street\s*light",
            r"streetlight",
            r"lamp\s*not\s*working",
            r"dark\s+street",
            r"light\s*outage",
            r"தெரு\s*விளக்கு",
            r"स्ट्रीट\s*लाइट",
        ],
    ),
    (
        CivicIntent.GARBAGE_ACCUMULATION,
        [
            r"garbage",
            r"trash",
            r"waste\s*accumulat",
            r"dustbin\s*overflow",
            r"rubbish",
            r"dump",
            r"குப்பை",
            r"कचरा",
            r"कूड़ा",
        ],
    ),
    (
        CivicIntent.WATER_SUPPLY_ISSUE,
        [
            r"no\s+water",
            r"water\s+supply",
            r"water\s+not\s+coming",
            r"tap\s*water",
            r"drinking\s+water",
            r"தண்ணீர்\s*வரவில்லை",
            r"पानी\s*नहीं\s*आ\s*रहा",
        ],
    ),
    (
        CivicIntent.ELECTRICITY_OUTAGE,
        [
            r"power\s*cut",
            r"electricity\s*outage",
            r"no\s+electricity",
            r"power\s+failure",
            r"sparking\s*wire",
            r"transformer",
            r"மின்சாரம்",
            r"बिजली\s*गुल",
        ],
    ),
    (
        CivicIntent.PUBLIC_INFRASTRUCTURE_DAMAGE,
        [
            r"footpath",
            r"pavement",
            r"traffic\s*signal",
            r"railing",
            r"bench",
            r"public\s+park",
        ],
    ),
]


def detect_language(text: str) -> str:
    """Detect language based on Unicode character blocks or common tokens."""
    # Tamil Unicode Block: \u0B80-\u0BFF
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "Tamil"
    # Devanagari (Hindi / Marathi) Block: \u0900-\u097F
    if re.search(r"[\u0900-\u097F]", text):
        return "Hindi"
    # Telugu Block: \u0C00-\u0C7F
    if re.search(r"[\u0C00-\u0C7F]", text):
        return "Telugu"
    # Kannada Block: \u0C80-\u0CFF
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "Kannada"
    # Bengali Block: \u0980-\u09FF
    if re.search(r"[\u0980-\u09FF]", text):
        return "Bengali"

    # Hinglish detection via common Romanized Hindi particles
    hinglish_tokens = ["kahan", "hai", "nahi", "raha", "pani", "yeh", "bahut", "sadak", "kaise", "karein", "ho"]
    words = [w.lower() for w in re.findall(r"\w+", text)]
    if any(tok in words for tok in hinglish_tokens):
        return "Hinglish"

    return "English"


class RequirementIntentAgent:
    """Agent 1: Requirement & Intent Analyzer."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def analyze_deterministic(self, message: str, language_hint: Optional[str] = None) -> IntentAnalysis:
        """Deterministic keyword-based intent classification for local resilience."""
        msg_lower = message.lower()
        detected = detect_language(message)
        if detected != "English":
            detected_lang = detected
        elif language_hint and language_hint.lower() not in ["en", "english"]:
            detected_lang = language_hint
        else:
            detected_lang = "English"

        # Check non-civic greetings or gibberish
        clean_msg = re.sub(r"[^\w\s]", "", msg_lower).strip()
        common_greetings = {
            "hi", "hello", "hey", "test", "good morning", "good evening", "good afternoon", "how are you"
        }
        words = clean_msg.split()
        is_greeting = (
            len(clean_msg) < 4
            or clean_msg in common_greetings
            or (words and all(w in ["hello", "hi", "hey", "good", "morning", "evening", "afternoon", "how", "are", "you", "there", "hope", "having", "a", "nice", "day", "thanks", "thank"] for w in words))
        )
        if is_greeting:
            return IntentAnalysis(
                intent=CivicIntent.OTHER_CIVIC_ISSUE,
                is_civic=False,
                language=detected_lang,
                confidence=0.5,
                initial_description=message.strip(),
            )

        # Match intent patterns
        for intent, patterns in INTENT_KEYWORD_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, msg_lower, re.IGNORECASE):
                    return IntentAnalysis(
                        intent=intent,
                        is_civic=True,
                        language=detected_lang,
                        confidence=0.85,
                        initial_description=message.strip(),
                    )

        # Default fallback
        return IntentAnalysis(
            intent=CivicIntent.OTHER_CIVIC_ISSUE,
            is_civic=True,
            language=detected_lang,
            confidence=0.6,
            initial_description=message.strip(),
        )

    async def run(self, message: str, language_hint: Optional[str] = None) -> IntentAnalysis:
        """Execute intent analysis: probes LLM if available, falls back gracefully."""
        status = await self.provider.check_health()
        if status == LLMStatus.LLM_AVAILABLE:
            prompt = f"Analyze citizen complaint:\n\"{message}\"\nLanguage hint: {language_hint or 'None'}"
            llm_result = await self.provider.generate_structured(
                prompt=prompt,
                response_model=IntentAnalysis,
                system_prompt=INTENT_ANALYZER_SYSTEM_PROMPT,
            )
            if llm_result:
                return llm_result

        # Graceful deterministic fallback
        return self.analyze_deterministic(message, language_hint)
