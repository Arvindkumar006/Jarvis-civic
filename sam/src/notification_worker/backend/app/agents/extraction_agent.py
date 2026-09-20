"""Agent 2: Civic Information Extractor.

Extracts physical geographic attributes (street, area, locality, landmark, 6-digit postal PIN code)
and explicit hazard indicators strictly from citizen text in ANY supported natural language.
Enforces the anti-hallucination mandate: never fabricate absent fields.
"""

import re
from typing import List, Optional, Tuple
from app.models.reasoning import CivicExtraction
from app.agents.prompts import CIVIC_EXTRACTOR_SYSTEM_PROMPT
from app.llm.provider import LLMProvider, LLMStatus

# Indic numeral transliteration map to standard ASCII 0-9
INDIC_DIGIT_MAP = str.maketrans({
    # Devanagari (Hindi, Marathi)
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    # Tamil
    "௦": "0", "௧": "1", "௨": "2", "௩": "3", "௪": "4", "௫": "5", "௬": "6", "௭": "7", "௮": "8", "௯": "9",
    # Telugu
    "౦": "0", "౧": "1", "౨": "2", "౩": "3", "౪": "4", "౫": "5", "౬": "6", "౭": "7", "౮": "8", "౯": "9",
    # Kannada
    "೦": "0", "೧": "1", "೨": "2", "೩": "3", "೪": "4", "೫": "5", "೬": "6", "೭": "7", "೮": "8", "೯": "9",
    # Bengali
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4", "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
})

# Recognized metropolitan centers & primary localities across major states in India
KNOWN_MUNICIPAL_LOCALITIES = [
    # Tamil Nadu / Greater Chennai
    ("Ambattur", ["ambattur", "அம்பத்தூர்", "அம்பத்தூரில்", "அம்பத்தூரு"]),
    ("Pudur", ["pudur", "புதூர்", "புதூரின்", "புதூரில்"]),
    ("Chennai", ["chennai", "சென்னை", "சென்னையில்", "மதராஸ்"]),
    ("Anna Nagar", ["anna nagar", "அண்ணா நகர்", "அண்ணாநகர்"]),
    ("Anna Salai", ["anna salai", "அண்ணா சாலை", "அண்ணா சாலையில்", "mount road"]),
    ("T Nagar", ["t nagar", "t. nagar", "தி நகர்", "தியாகராய நகர்"]),
    ("Guindy", ["guindy", "கிண்டி", "கிண்டியில்"]),
    ("Velachery", ["velachery", "வேளச்சேரி", "வேளச்சேரியில்"]),
    ("Adyar", ["adyar", "அடையாறு", "அடையாறில்"]),
    ("Avadi", ["avadi", "ஆவடி", "ஆவடியில்"]),
    ("Tambaram", ["tambaram", "தாம்பரம்", "தாம்பரத்தில்"]),
    ("Porur", ["porur", "போரூர்", "போரூரில்"]),
    ("Mylapore", ["mylapore", "மயிலாப்பூர்", "மயிலாப்பூரில்"]),
    ("Koyambedu", ["koyambedu", "கோயம்பேடு", "கோயம்பேட்டில்"]),
    ("Perambur", ["perambur", "பெரம்பூர்", "பெரம்பூரில்"]),
    ("Chromepet", ["chromepet", "குரோம்பேட்டை"]),
    ("Madhavaram", ["madhavaram", "மாதவரம்"]),
    ("Saidapet", ["saidapet", "சைதாப்பேட்டை"]),
    ("Thousand Lights", ["thousand lights", "ஆயிரம் விளக்கு"]),
    ("Royapettah", ["royapettah", "ராயப்பேட்டை"]),
    ("Sholinganallur", ["sholinganallur", "சோழிங்கநல்லூர்"]),
    ("OMR", ["omr", "old mahabalipuram road"]),
    # Karnataka / Bengaluru
    ("Bengaluru", ["bengaluru", "bangalore", "ಬೆಂಗಳೂರು", "ಬೆಂಗಳೂರಿನಲ್ಲಿ", "बेंगलुरु", "பெங்களூரு"]),
    ("Koramangala", ["koramangala", "ಕೋರಮಂಗಲ", "ಕೋರಮಂಗಲದಲ್ಲಿ"]),
    ("Indiranagar", ["indiranagar", "ಇಂದಿರಾನಗರ"]),
    ("Whitefield", ["whitefield", "ವೈಟ್‌ಫೀಲ್ಡ್"]),
    ("HSR Layout", ["hsr layout", "ಎಚ್‌ಎಸ್‌ಆರ್ ಲೇಔಟ್"]),
    ("Majestic", ["majestic", "ಮೆಜೆಸ್ಟಿಕ್"]),
    # Delhi NCR
    ("Delhi", ["delhi", "new delhi", "दिल्ली", "டெல்லி", "ದೆಹಲಿ"]),
    ("Chandni Chowk", ["chandni chowk", "चांदनी चौक"]),
    ("Connaught Place", ["connaught place", "कनॉट प्लेस", "cp"]),
    ("Karol Bagh", ["karol bagh", "करोल बाग"]),
    ("Laxmi Nagar", ["laxmi nagar", "लक्ष्मी नगर"]),
    ("Gurgaon", ["gurgaon", "gurugram", "गुड़गांव", "गुरुग्राम"]),
    ("Noida", ["noida", "नोएडा"]),
    # Maharashtra / Mumbai & Pune
    ("Mumbai", ["mumbai", "bombay", "मुंबई", "மும்பை"]),
    ("Pune", ["pune", "पुणे", "पुण्यात", "புனே"]),
    ("Dadar", ["dadar", "दादर"]),
    ("Andheri", ["andheri", "अंधेरी"]),
    ("Bandra", ["bandra", "बांद्रा"]),
    ("Kothrud", ["kothrud", "कोथरूड"]),
    ("Shivaji Nagar", ["shivaji nagar", "शिवाजी नगर"]),
    # Telangana & AP / Hyderabad
    ("Hyderabad", ["hyderabad", "హైదరాబాద్", "हैदराबाद", "ஹைதராபாத்"]),
    ("Banjara Hills", ["banjara hills", "బంజారా హిల్స్"]),
    ("Ameerpet", ["ameerpet", "అమీర్‌పేట్"]),
    ("Secunderabad", ["secunderabad", "సికింద్రాబాద్"]),
    # West Bengal / Kolkata
    ("Kolkata", ["kolkata", "calcutta", "কলকাতা", "कोलकाता"]),
    ("Salt Lake", ["salt lake", "সল্টলেক", "সল্ট লেক"]),
    ("Howrah", ["howrah", "হাওড়া"]),
    ("Shyambazar", ["shyambazar", "শ্যামবাজার"]),
]

STREET_SUFFIX_PATTERN = (
    r"(?:Main\s*Road|Cross\s*Road|Road|Street|Salai|Marg|Nagar|Colony|Sector|Layout|Cross|Main|Lane|Avenue|Bazaar|Market|Chowk|Circle|Flyover|Bus Stand|Station|Metro|Rd|St|"
    r"தெரு|சாலை|நகர்|சந்து|வட்டம்|பகுதி|ஊர்|பேருந்து\s*நிலையம்|நிலையம்|பாலம்|சந்தை|ரவுண்டானா|மெயின்\s*ரோடு|"
    r"मार्ग|सड़क|गली|नगर|कॉलोनी|चौक|बाजार|स्टेशन|पुल|बस\s*स्टैंड|"
    r"వీధి|రోడ్డు|నగర్|కాలనీ|చౌరస్తా|స్టేషన్|"
    r"ರಸ್ತೆ|ಬಡಾವಣೆ|ನಗರ|ವೃತ್ತ|ನಿಲ್ದಾಣ|"
    r"রাস্তা|সড়ক|নগর|মোড়|স্টেশন|"
    r"रस्ता|मार्ग|नगर|कॉलनी|चौक)"
)

UNICODE_CHAR_SET = r"[A-Za-z0-9\u0B80-\u0BFF\u0900-\u097F\u0C00-\u0C7F\u0C80-\u0CFF\u0980-\u09FF\s,\-\.\']"


class CivicExtractionAgent:
    """Agent 2: Civic Information Extractor."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def extract_deterministic(self, message: str) -> CivicExtraction:
        """Deterministic extraction using exact regex for PIN code, locations, and hazards."""
        # 1. PIN code extraction: Standalone 6-digit Indian PIN code matching ^[1-9][0-9]{5}$
        pincode: Optional[str] = None
        norm_message = message.translate(INDIC_DIGIT_MAP)
        pin_match = re.search(r"(?<!\d)([1-9][0-9]{5})(?!\d)", norm_message)
        if pin_match:
            pincode = pin_match.group(1)

        # 2. Hazard extraction across languages
        hazard_flags: List[str] = []
        msg_lower = message.lower()

        # Electrical hazards
        if re.search(
            r"\b(live\s*wire|exposed\s*wire|sparking\s*wire|hanging\s*wire|sparking|transformer)\b"
            r"|மின்சாரம்|மின்\s*கம்பி|மின்கம்பி|மின்சாரம்\s*தாக்கும்"
            r"|बिजली\s*का\s*तार|करंट|करंट\s*लगने"
            r"|కరెంట్\s*తీగలు|లైవ్\s*వైర్"
            r"|ವಿದ್ಯುತ್\s*ತಂತಿ"
            r"|ছেঁড়া\s*তার",
            msg_lower,
            re.IGNORECASE,
        ):
            hazard_flags.append("Live electrical wire hazard")

        # Open pit / manhole hazards
        if re.search(
            r"\b(open\s*manhole|deep\s*hole|open\s*drain|manhole)\b"
            r"|திறந்த\s*மேன்ஹோல்|பாதாள\s*சாக்கடை|ஆழமான\s*பள்ளம்"
            r"|खुला\s*मैनहोल|खुला\s*गड्ढा|खुला\s*नाला"
            r"|తెరిచి\s*ఉన్న\s*మ్యాన్‌హోల్"
            r"|ತೆರೆದ\s*ಮ್ಯಾನ್‌ಹೋಲ್"
            r"|খোলা\s*ম্যানহোল",
            msg_lower,
            re.IGNORECASE,
        ):
            hazard_flags.append("Open manhole or pedestrian pit hazard")

        # Ingress / Home flooding hazards
        if re.search(
            r"\b(water\s*inside\s*house|flooding\s*home|flooding\s*hospital|flooded\s*house)\b"
            r"|வீட்டுக்குள்\s*தண்ணீர்|வீட்டிற்குள்\s*வெள்ளம்"
            r"|घर\s*में\s*पानी|अस्पताल\s*में\s*पानी"
            r"|ఇంట్లోకి\s*నీరు"
            r"|ಮನೆಗೆ\s*ನೀರು"
            r"|বাড়িতে\s*জল",
            msg_lower,
            re.IGNORECASE,
        ):
            hazard_flags.append("Residential or hospital water ingress")

        # Corridor blockage
        if re.search(r"\b(ambulance|hospital\s*route|arterial\s*road)\b|ஆம்புலன்ஸ்|அவசர\s*வழி", msg_lower, re.IGNORECASE):
            hazard_flags.append("Emergency transit corridor blockage")

        # 3. Landmark extraction (Prepositions AND Postpositions)
        landmark: Optional[str] = None

        # A. Preposition prefixes: "near <Place>", "opposite <Place>", "அருகில் <Place>", etc.
        prep_prefix_match = re.search(
            r"(?:\b(?:near|opposite|opp|behind|beside|next\s+to|in\s+front\s+of|adjacent\s+to)\s+"
            r"|அருகில்\s+|எதிரில்\s+|பின்னால்\s+|பக்கத்தில்\s+|கிட்ட\s+|பக்கத்துல\s+)"
            rf"({UNICODE_CHAR_SET}{{2,40}}?)(?:\.|\,|$|\bat\b|\bon\b|\bin\b)",
            message,
            re.IGNORECASE,
        )
        if prep_prefix_match:
            cand = prep_prefix_match.group(1).strip()
            if 2 <= len(cand.split()) <= 6:
                landmark = cand

        # B. Postposition suffixes: "<Place> அருகில்", "<Place> எதிரில்", "<Place> ke paas", "<Place> దగ్గర", etc.
        if not landmark:
            post_suffix_match = re.search(
                rf"({UNICODE_CHAR_SET}{{2,35}})\s*"
                r"(?:அருகில்|எதிரில்|பின்னால்|பக்கத்தில்|கிட்ட|பக்கத்துல"
                r"|के\s+पास|के\s+सामने|के\s+पीछे|के\s+बगल\s+में|pass|ke\s+paas"
                r"|దగ్గర|ఎదురుగా|వెనుక|పక్కన"
                r"|ಹತ್ತಿರ|ಎದುರು|ಹಿಂದೆ|ಪಕ್ಕದಲ್ಲಿ"
                r"|কাছে|সামনে|পেছনে|পাশে"
                r"|जवळ|समोर|मागे|शेजारी)(?:\.|\,|$|\s)",
                message,
                re.IGNORECASE,
            )
            if post_suffix_match:
                cand = post_suffix_match.group(1).strip()
                # Clean leading prepositions if captured
                cand = re.sub(r"^(?:in|at|on|there\s+is\s+a|பள்ளம்|ரோடு|கழிவுநீர்|தண்ணீர்)\s+", "", cand, flags=re.IGNORECASE).strip()
                if 1 <= len(cand.split()) <= 6 and len(cand) >= 2:
                    landmark = cand

        # 4. Multilingual Physical Location Component Extraction (Street, Area, Locality)
        street: Optional[str] = None
        area: Optional[str] = None
        locality: Optional[str] = None
        location: Optional[str] = None

        # Check for explicit street mention matching street suffixes (e.g. "Kumaran Street", "குமரன் தெரு", "चांदनी चौक")
        street_match = re.search(
            rf"({UNICODE_CHAR_SET}{{2,30}}\s*{STREET_SUFFIX_PATTERN})",
            message,
            re.IGNORECASE,
        )
        if street_match:
            cand_street = street_match.group(1).strip()
            # Clean common noise prefixes and defect words from cand_street
            cand_street = re.sub(
                r"^(?:in|at|on|near|there\s+is|a|pothole\s+near|pothole|waterlogging|garbage|streetlight|"
                r"ஒரு|ஒரு\s+பள்ளம்|பள்ளம்|கழிவுநீர்|தண்ணீர்|गड्ढा\s+है|गड्ढा|जलभराव|पानी|குப்பை)\s+",
                "",
                cand_street,
                flags=re.IGNORECASE,
            ).strip()
            # Clean trailing postposition particles
            cand_street = re.sub(
                r"\s+(?:ke\s+paas|near|pass|அருகில்|எதிரில்|దగ్గర|ಹತ್ತಿರ)\b.*$",
                "",
                cand_street,
                flags=re.IGNORECASE,
            ).strip()
            if len(cand_street) >= 3:
                street = cand_street

        # Check for known municipalities / localities (e.g. "Ambattur", "Pudur", "Chennai", "Delhi", "Bengaluru", "Pune")
        matched_localities: List[Tuple[int, str, str]] = []
        for canonical_name, variants in KNOWN_MUNICIPAL_LOCALITIES:
            for variant in variants:
                # Match as whole token or sub-token boundary
                pat = rf"(?:^|[\s,\-\'\"]){re.escape(variant)}(?:$|[\s,\-\'\"\.]|இல்|ல்|లో|में|पर|তে|এ|मध्ये|त|ನಲ್ಲಿ|ದಲ್ಲಿ)"
                m_loc = re.search(pat, message, re.IGNORECASE)
                if m_loc:
                    # Capture the actual matched string slice from the message to preserve original language script
                    m_sub = re.search(re.escape(variant), message, re.IGNORECASE)
                    disp = m_sub.group(0) if m_sub else variant
                    pos = m_sub.start() if m_sub else m_loc.start()
                    matched_localities.append((pos, canonical_name, disp))
                    break

        if matched_localities:
            # Sort by position of occurrence in message to distinguish Street / Area / Locality
            matched_localities.sort(key=lambda x: x[0])
            if len(matched_localities) == 1:
                locality = matched_localities[0][2]
            else:
                area = matched_localities[0][2]
                locality = matched_localities[1][2]


        # Check locative case suffixes if locality/street not yet captured
        # Tamil locative: "<Word>இல்" or "<Word>ல்" (e.g. "அம்பத்தூரில்", "சென்னையில்", "ரோட்டில்")
        if not locality:
            ta_loc_match = re.search(r"([A-Za-z\u0B80-\u0BFF]{3,25})(?:இல்|ல்)(?:\s|$|\,)", message)
            if ta_loc_match:
                cand_loc = ta_loc_match.group(1).strip()
                if not cand_loc.startswith(("ரோட்", "சாலை", "தெரு", "தண்ணீ", "குப்ப", "பள்ள", "பிரச்சனை")):
                    locality = cand_loc

        # Hindi locative: "<Word> में" or "<Word> पर" (e.g. "चांदनी चौक में", "पुणे में")
        if not locality:
            hi_loc_match = re.search(rf"({UNICODE_CHAR_SET}{{2,30}})\s*(?:में|पर|पे)(?:\s|$|\,)", message, re.IGNORECASE)
            if hi_loc_match:
                cand_loc = hi_loc_match.group(1).strip()
                cand_loc = re.sub(r"^(?:गड्ढा|जलभराव|पानी|कचरा|समस्या)\s+(?:है\s+)?", "", cand_loc).strip()
                if len(cand_loc) >= 2 and not cand_loc.startswith(("सड़क", "रोड", "गली", "रास्ता")):
                    locality = cand_loc

        # Telugu locative: "<Word>లో" (e.g. "అంబత్తూరులో")
        if not locality:
            te_loc_match = re.search(r"([A-Za-z\u0C00-\u0C7F]{3,25})లో(?:\s|$|\,)", message)
            if te_loc_match:
                cand_loc = te_loc_match.group(1).strip()
                if not cand_loc.startswith(("నీరు", "సమస్య", "రోడ్డు", "వీధి")):
                    locality = cand_loc

        # Kannada locative: "<Word>ನಲ್ಲಿ" or "<Word>ದಲ್ಲಿ"
        if not locality:
            kn_loc_match = re.search(r"([A-Za-z\u0C80-\u0CFF]{3,25})(?:ನಲ್ಲಿ|ದಲ್ಲಿ)(?:\s|$|\,)", message)
            if kn_loc_match:
                cand_loc = kn_loc_match.group(1).strip()
                if not cand_loc.startswith(("ನೀರು", "ಸಮಸ್ಯೆ", "ರಸ್ತೆ")):
                    locality = cand_loc

        # Bengali locative: "<Word>তে" or "<Word>এ"
        if not locality:
            bn_loc_match = re.search(r"([A-Za-z\u0980-\u09FF]{3,25})(?:তে|এ)(?:\s|$|\,)", message)
            if bn_loc_match:
                cand_loc = bn_loc_match.group(1).strip()
                if not cand_loc.startswith(("জল", "সমস্যা", "রাস্তা")):
                    locality = cand_loc

        # Marathi locative: "<Word>मध्ये" or "<Word>त"
        if not locality:
            mr_loc_match = re.search(r"([A-Za-z\u0900-\u097F]{3,25})(?:मध्ये|त)(?:\s|$|\,)", message)
            if mr_loc_match:
                cand_loc = mr_loc_match.group(1).strip()
                if not cand_loc.startswith(("पाणी", "खड्डा", "रस्ता")):
                    locality = cand_loc

        # Assemble unified comprehensive location string
        loc_parts: List[str] = []
        if street and street not in loc_parts:
            loc_parts.append(street)
        if area and area not in loc_parts and (not street or area not in street):
            loc_parts.append(area)
        if locality and locality not in loc_parts and (not street or locality not in street):
            loc_parts.append(locality)
        if landmark and loc_parts and landmark not in loc_parts and (not street or landmark.lower() not in street.lower()):
            loc_parts.append(landmark)

        if loc_parts:
            location = ", ".join(loc_parts)
        else:
            location = None

        return CivicExtraction(
            description=message.strip(),
            location=location,
            street=street,
            area=area,
            locality=locality,
            landmark=landmark,
            pincode=pincode,
            hazard_flags=hazard_flags,
        )

    async def run(self, message: str) -> CivicExtraction:
        """Run extraction using local model when healthy; otherwise deterministic fallback."""
        status = await self.provider.check_health()
        if status == LLMStatus.LLM_AVAILABLE:
            prompt = (
                f"Extract physical street, area, locality, landmark, 6-digit Indian PIN code, and hazards from:\n"
                f"\"{message}\"\n"
                f"Reminder: Retain original language names (do not force English transliteration). If absent, return null. Never fabricate."
            )
            llm_result = await self.provider.generate_structured(
                prompt=prompt,
                response_model=CivicExtraction,
                system_prompt=CIVIC_EXTRACTOR_SYSTEM_PROMPT,
            )
            if llm_result and (llm_result.location or llm_result.street or llm_result.locality or llm_result.pincode):
                return llm_result

        return self.extract_deterministic(message)

