"""Evidence Assessment Provider Abstraction for JARVIS Civic.

Phase 8.7: Advisory AI assessment provider interface and implementations.
AI assessment is strictly advisory and NEVER closes a case or marks it RESOLVED.
Falls back safely to UNCERTAIN when AI providers are unavailable or fail.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from app.config.settings import settings
from app.models.evidence import EvidenceType, VerificationOutcome

logger = logging.getLogger("jarvis.evidence.provider")


class EvidenceAssessmentResult:
    """Structured result returned by an EvidenceAssessmentProvider."""

    def __init__(
        self,
        outcome: VerificationOutcome,
        reason: str,
        detected_characteristics: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        provider_id: str = "deterministic-fallback",
        model_id: Optional[str] = None,
        ai_available: bool = False,
    ):
        self.outcome = outcome
        self.reason = reason
        self.detected_characteristics = detected_characteristics or []
        self.confidence = confidence
        self.provider_id = provider_id
        self.model_id = model_id
        self.ai_available = ai_available
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "detected_characteristics": self.detected_characteristics,
            "confidence": self.confidence,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "ai_available": self.ai_available,
            "timestamp": self.timestamp.isoformat(),
        }


class EvidenceAssessmentProvider(ABC):
    """Abstract base class for advisory evidence assessment providers."""

    @abstractmethod
    def assess(
        self,
        case_id: str,
        case_description: str,
        department: str,
        evidence_type: EvidenceType,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        resolution_attempt: Optional[str] = None,
    ) -> EvidenceAssessmentResult:
        """Analyze evidence within case context and return structured advisory assessment."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider backend is reachable and ready."""
        pass


class DeterministicFallbackProvider(EvidenceAssessmentProvider):
    """Safe fallback provider when AI assessment is disabled or unavailable.

    Always returns canonical UNCERTAIN outcome with truthful reasoning.
    """

    def is_available(self) -> bool:
        return False

    def assess(
        self,
        case_id: str,
        case_description: str,
        department: str,
        evidence_type: EvidenceType,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        resolution_attempt: Optional[str] = None,
    ) -> EvidenceAssessmentResult:
        return EvidenceAssessmentResult(
            outcome=VerificationOutcome.UNCERTAIN,
            reason="AI assessment unavailable or offline; deterministic file validation passed.",
            detected_characteristics=["deterministic_validation_passed"],
            confidence=None,
            provider_id="deterministic-fallback",
            model_id=None,
            ai_available=False,
        )


import base64

def is_multimodal_vision_model(model_name: str) -> bool:
    """Determine whether an Ollama model genuinely supports visual image inspection."""
    name = (model_name or "").lower()
    vision_indicators = [
        "vision", "llava", "bakllava", "moondream", "minicpm-v", "qwen-vl", "cogvlm"
    ]
    return any(ind in name for ind in vision_indicators)


class OllamaEvidenceAssessmentProvider(EvidenceAssessmentProvider):
    """Local advisory assessment provider utilizing local Ollama runtime.

    Gracefully falls back to UNCERTAIN if Ollama is unreachable, model fails,
    or the model does not support the artifact modality.
    """

    def __init__(self, endpoint_url: Optional[str] = None, model: Optional[str] = None):
        self.endpoint_url = (endpoint_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or getattr(settings, "JARVIS_LLM_MODEL", "llama3.2:3b")

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.endpoint_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def assess(
        self,
        case_id: str,
        case_description: str,
        department: str,
        evidence_type: EvidenceType,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        resolution_attempt: Optional[str] = None,
    ) -> EvidenceAssessmentResult:
        # Check artifact modality
        is_image = content_type.startswith("image/")
        is_audio = content_type.startswith("audio/")
        is_text = content_type == "text/plain" or filename.endswith(".txt")

        # Modality check 1: Image artifacts require a multimodal vision model
        if is_image and not is_multimodal_vision_model(self.model):
            logger.info(
                "Model '%s' is text-only; cannot inspect image '%s'. Returning safe UNCERTAIN.",
                self.model, filename,
            )
            return EvidenceAssessmentResult(
                outcome=VerificationOutcome.UNCERTAIN,
                reason=f"Configured model '{self.model}' is text-only and does not support image analysis; deterministic validation passed without AI assessment.",
                detected_characteristics=["unsupported_modality", "text_only_model"],
                confidence=None,
                provider_id="ollama",
                model_id=self.model,
                ai_available=False,
            )

        # Modality check 2: Audio artifacts are not processed by text/vision LLM
        if is_audio:
            return EvidenceAssessmentResult(
                outcome=VerificationOutcome.UNCERTAIN,
                reason="Audio artifact modality is not supported by configured model; deterministic validation passed without AI assessment.",
                detected_characteristics=["unsupported_audio_modality"],
                confidence=None,
                provider_id="ollama",
                model_id=self.model,
                ai_available=False,
            )

        if not self.is_available():
            logger.info("Ollama provider offline; returning safe UNCERTAIN outcome")
            return EvidenceAssessmentResult(
                outcome=VerificationOutcome.UNCERTAIN,
                reason="Local AI provider offline; deterministic validation passed without AI assessment.",
                detected_characteristics=["ai_offline", "deterministic_only"],
                confidence=None,
                provider_id="ollama",
                model_id=self.model,
                ai_available=False,
            )

        # Construct multimodal or text prompt
        if is_image:
            prompt = (
                f"You are an advisory civic evidence assessor. Inspect this uploaded image to assess whether "
                f"it provides visual evidence consistent with the case.\n"
                f"Case Context: {case_description}\n"
                f"Department: {department}\n"
                f"Evidence Type: {evidence_type.value}\n"
                f"Resolution Reference: {resolution_attempt or 'None'}\n\n"
                f"Respond ONLY with a JSON object with keys: "
                f"'outcome' (one of: VERIFIED, LIKELY_VERIFIED, UNCERTAIN, REJECTED), "
                f"'reason' (concise explanation up to 200 characters), "
                f"'characteristics' (list of observed features), "
                f"'confidence' (float 0.0 to 1.0 or null)."
            )
            images_payload = [base64.b64encode(file_bytes).decode("ascii")]
        else:
            text_sample = file_bytes[:4000].decode("utf-8", errors="replace")
            prompt = (
                f"You are an advisory civic evidence assessor. Evaluate whether the following document content "
                f"is consistent with the case.\n"
                f"Case Context: {case_description}\n"
                f"Department: {department}\n"
                f"Evidence Type: {evidence_type.value}\n"
                f"Resolution Reference: {resolution_attempt or 'None'}\n"
                f"Document text sample:\n{text_sample}\n\n"
                f"Respond ONLY with a JSON object with keys: "
                f"'outcome' (one of: VERIFIED, LIKELY_VERIFIED, UNCERTAIN, REJECTED), "
                f"'reason' (concise explanation up to 200 characters), "
                f"'characteristics' (list of observed features), "
                f"'confidence' (float 0.0 to 1.0 or null)."
            )
            images_payload = []

        try:
            req_dict = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
            if images_payload:
                req_dict["images"] = images_payload

            payload = json.dumps(req_dict).encode("utf-8")
            req = urllib.request.Request(
                f"{self.endpoint_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "{}")
                parsed = json.loads(response_text)

                raw_outcome = str(parsed.get("outcome", "UNCERTAIN")).upper()
                if raw_outcome not in VerificationOutcome.__members__:
                    outcome = VerificationOutcome.UNCERTAIN
                else:
                    outcome = VerificationOutcome(raw_outcome)

                raw_conf = parsed.get("confidence")
                conf = float(raw_conf) if isinstance(raw_conf, (int, float)) and 0.0 <= raw_conf <= 1.0 else None

                return EvidenceAssessmentResult(
                    outcome=outcome,
                    reason=str(parsed.get("reason", "Assessment completed."))[:300],
                    detected_characteristics=list(parsed.get("characteristics", []))[:5],
                    confidence=conf,
                    provider_id="ollama",
                    model_id=self.model,
                    ai_available=True,
                )
        except Exception as exc:
            logger.warning("Ollama assessment failed or returned malformed data: %s", exc)
            return EvidenceAssessmentResult(
                outcome=VerificationOutcome.UNCERTAIN,
                reason="Advisory AI evaluation encountered an internal error; defaulted to UNCERTAIN.",
                detected_characteristics=["evaluation_error"],
                confidence=None,
                provider_id="ollama",
                model_id=self.model,
                ai_available=False,
            )



class MockEvidenceAssessmentProvider(EvidenceAssessmentProvider):
    """Test-only deterministic assessment provider for isolated verification."""

    def __init__(
        self,
        outcome: VerificationOutcome = VerificationOutcome.VERIFIED,
        reason: str = "Test advisory verification matched case context.",
        confidence: Optional[float] = 0.88,
        ai_available: bool = True,
        characteristics: Optional[List[str]] = None,
    ):
        self.outcome = outcome
        self.reason = reason
        self.confidence = confidence
        self.available = ai_available
        self.characteristics = characteristics or ["test_feature_detected"]

    def is_available(self) -> bool:
        return self.available

    def assess(
        self,
        case_id: str,
        case_description: str,
        department: str,
        evidence_type: EvidenceType,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        resolution_attempt: Optional[str] = None,
    ) -> EvidenceAssessmentResult:
        if not self.available:
            return EvidenceAssessmentResult(
                outcome=VerificationOutcome.UNCERTAIN,
                reason="Mock AI provider marked unavailable.",
                detected_characteristics=["mock_unavailable"],
                confidence=None,
                provider_id="mock-provider",
                model_id="mock-model",
                ai_available=False,
            )

        return EvidenceAssessmentResult(
            outcome=self.outcome,
            reason=self.reason,
            detected_characteristics=self.characteristics,
            confidence=self.confidence,
            provider_id="mock-provider",
            model_id="mock-model",
            ai_available=True,
        )
