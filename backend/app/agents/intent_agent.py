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
            r"जल\s*জমে",
            r"জল",
            r"पाणी\s*साचले",
            r"నీరు\s*నిలిచి",
            r"నీరు",
            r"ನೀರು\s*ನಿಂತಿದೆ",
            r"ನೀರು",
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
            r"नाली\s*जाम",
            r"गंदा\s*पानी",
            r"డ్రైనేజీ",
            r"కాలువ",
            r"ಚರಂಡಿ",
            r"নর্দমা",
            r"गटार",
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
            r"பள்ளம்",
            r"குழி",
            r"सड़क\s*खराब",
            r"गड्ढा",
            r"गड्ढे",
            r"खड्डा",
            r"खड्डे",
            r"గుంత",
            r"గుంటలు",
            r"ಗುಂಡಿ",
            r"ರಸ್ತೆ\s*ಗುಂಡಿ",
            r"খানাখন্দ",
            r"ভাঙা\s*রাস্তা",
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
            r"விளக்கு\s*எரியவில்லை",
            r"स्ट्रीट\s*लाइट",
            r"बत्ती\s*गुल",
            r"లైట్\s*పనిచేయట్లేదు",
            r"బల్బు",
            r"ಬೀದಿ\s*ದೀಪ",
            r"পথবাति",
            r"दिवा\s*बंद",
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
            r"குப்பை\s*மேடு",
            r"कचरा",
            r"कूड़ा",
            r"घाण",
            r"చెత్త",
            r"చెత్తా\s*చెదారం",
            r"ಕಸ",
            r"আবর্জনা",
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
            r"குடிநீர்",
            r"पानी\s*नहीं\s*आ\s*रहा",
            r"नहाने\s*का\s*पानी",
            r"నీటి\s*సరఫరా",
            r"ನೀರಿನ\s*ಸಮಸ್ಯೆ",
            r"পানীয়\s*জল",
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
            r"மின்வெட்டு",
            r"बिजली\s*गुल",
            r"కరెంట్\s*లేదు",
            r"ವಿದ್ಯುತ್\s*ಕಡಿತ",
            r"বিদ্যুৎ\s*বিভ্রাট",
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
            r"நடைபாதை",
            r"फुटपाथ",
            r"ఫుట్‌పాత్",
            r"ಕಾಲುದಾರಿ",
        ],
    ),
]


def detect_language(text: str, hint: Optional[str] = None) -> str:
    """Detect language based on Unicode character blocks, common tokens, or language hint."""
    # 1. Unicode script detection (authoritative for non-Latin scripts)
    # Tamil Unicode Block: \u0B80-\u0BFF
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "Tamil"
    # Telugu Block: \u0C00-\u0C7F
    if re.search(r"[\u0C00-\u0C7F]", text):
        return "Telugu"
    # Kannada Block: \u0C80-\u0CFF
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "Kannada"
    # Bengali Block: \u0980-\u09FF
    if re.search(r"[\u0980-\u09FF]", text):
        return "Bengali"
    # Devanagari (Hindi / Marathi) Block: \u0900-\u097F
    if re.search(r"[\u0900-\u097F]", text):
        # Disambiguate Marathi vs Hindi based on Marathi markers
        if re.search(r"\b(आहे|झाला|झाली|नाही|आहेत|पुणे|रस्त्यावर|कॉलनी)\b", text):
            return "Marathi"
        return "Hindi"

    # 2. Hinglish detection via common Romanized Hindi particles
    hinglish_tokens = ["kahan", "hai", "nahi", "raha", "pani", "yeh", "bahut", "sadak", "kaise", "karein", "ho", "mein", "gaddha", "paas", "ke"]
    words = [w.lower() for w in re.findall(r"\w+", text)]
    if any(tok in words for tok in hinglish_tokens):
        return "Hinglish"

    # 3. Hint-based detection if Latin text
    if hint:
        hint_lower = hint.lower()
        if "ta" in hint_lower or "tamil" in hint_lower:
            return "Tamil"
        if "hi" in hint_lower or "hindi" in hint_lower:
            return "Hindi"
        if "te" in hint_lower or "telugu" in hint_lower:
            return "Telugu"
        if "kn" in hint_lower or "kannada" in hint_lower:
            return "Kannada"
        if "bn" in hint_lower or "bengali" in hint_lower:
            return "Bengali"
        if "mr" in hint_lower or "marathi" in hint_lower:
            return "Marathi"
        if "hinglish" in hint_lower:
            return "Hinglish"

    return "English"



class RequirementIntentAgent:
    """Agent 1: Requirement & Intent Analyzer."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def analyze_deterministic(self, message: str, language_hint: Optional[str] = None) -> IntentAnalysis:
        """Deterministic keyword-based intent classification for local resilience."""
        msg_lower = message.lower()
        detected_lang = detect_language(message, language_hint)

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

        # Check non-civic queries (math, poetry, trivia, coding, general knowledge)
        non_civic_patterns = [
            r"\b(poem|poetry|rhyme|song|sing|lyrics)\b",
            r"\b(capital\s+of|president\s+of|prime\s+minister\s+of|who\s+is|who\s+won)\b",
            r"\b(solve|math|equation|calculate\s+\d|formula|algebra)\b",
            r"\b(recipe|cook|baking|movie|film|actor|cricket|football)\b",
            r"\b(write\s+code|python\s+script|javascript\s+function|debug\s+this)\b",
            r"\b(joke|riddle|funny\s+story|tell\s+me\s+a)\b",
        ]
        if any(re.search(pat, msg_lower, re.IGNORECASE) for pat in non_civic_patterns):
            return IntentAnalysis(
                intent=CivicIntent.OTHER_CIVIC_ISSUE,
                is_civic=False,
                language=detected_lang,
                confidence=0.9,
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

        # Broad civic indicator keywords to prevent classifying arbitrary off-topic queries as civic
        broad_civic_keywords = [
            "road", "street", "water", "drain", "light", "garbage", "trash", "clean", "waste",
            "leak", "pothole", "traffic", "encroachment", "bridge", "flyover", "park", "manhole",
            "pipeline", "sewage", "gutter", "signal", "lamp", "sidewalk", "footpath", "complaint",
            "nagar", "colony", "ward", "corporation", "municipality", "panchayat", "civic",
            "area", "lane", "avenue", "junction", "sector", "block", "house", "building",
            "ambattur", "pudur", "chennai", "salai", "delhi", "bengaluru", "mumbai", "pune", "hyderabad", "kolkata",
            # Tamil
            "சாலை", "தெரு", "தண்ணீர்", "குப்பை", "விளக்கு", "பள்ளம்", "அம்பத்தூர்", "புதூர்", "சென்னை",
            "கிண்டி", "அடையாறு", "மயிலாப்பூர்", "ஊர்", "பகுதி", "வட்டம்", "சந்து", "குழி", "கழிவுநீர்", "சாக்கடை",
            # Hindi
            "सड़क", "गली", "पानी", "कचरा", "बिजली", "गड्ढा", "चांदनी", "चौक", "मार्ग", "बाजार", "नाला",
            # Telugu
            "రోడ్డు", "వీధి", "గుంత", "నీరు", "చెత్త", "అంబత్తూరు", "హైదరాబాద్",
            # Kannada
            "ರಸ್ತೆ", "ಗುಂಡಿ", "ನೀರು", "ಕಸ", "ಬೆಂಗಳೂರು",
            # Bengali
            "রাস্তা", "চৌরাস্তা", "জল", "আবর্জনা", "কলকাতা",
            # Marathi
            "रस्ता", "खड्डा", "पाणी", "पुणे", "कॉलनी",
        ]
        has_civic_term = any(term in msg_lower for term in broad_civic_keywords)
        if not has_civic_term:
            return IntentAnalysis(
                intent=CivicIntent.OTHER_CIVIC_ISSUE,
                is_civic=False,
                language=detected_lang,
                confidence=0.7,
                initial_description=message.strip(),
            )


        # Default fallback for unclassified civic issue
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
