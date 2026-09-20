"""Citizen Evidence Vision AI Relevance Service for JARVIS Civic.

Evaluates whether citizen-attached image evidence is visually relevant to the
reported civic issue (query).
Allowed outcomes: RELATED | NOT_RELATED | UNCERTAIN.
Advisory only: does NOT modify lifecycle, delete grievance, or alter department routing.
Safe fail-closed: UNCERTAIN on any model unavailability, text-only model, timeout, or parsing error.
"""

import base64
from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable, Dict, List, Optional
import urllib.error
import urllib.request

from app.config.settings import settings
from app.models.evidence_relevance import (
    CitizenEvidenceAssessment,
    EvidenceRelevanceOutcome,
)
from app.services.evidence.provider import is_multimodal_vision_model

logger = logging.getLogger("jarvis.evidence.vision")


class CitizenEvidenceVisionService:
    """Authoritative service for evaluating visual relevance of citizen evidence."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        vision_model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.endpoint_url = (endpoint_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.vision_model = vision_model or getattr(settings, "OLLAMA_VISION_MODEL", "llama3.2-vision")
        # Use a generous timeout for vision inference — CPU-only models like moondream
        # can take 60-90s for image analysis. LLM_TIMEOUT_SECONDS is for text only.
        self.timeout = timeout or 90.0
        self._custom_caller: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    def set_custom_caller(self, caller: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]) -> None:
        """Set a test hook caller for deterministic unit testing of vision outcomes."""
        self._custom_caller = caller

    def is_model_available(self) -> bool:
        """Check if configured vision model is reachable, installed, and vision-capable."""
        if self._custom_caller is not None:
            return True

        if not is_multimodal_vision_model(self.vision_model):
            return False

        try:
            req = urllib.request.Request(f"{self.endpoint_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status != 200:
                    return False
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                installed_names = [m.get("name", "").lower() for m in models]
                target = self.vision_model.lower()
                # Match exact name or base tag (e.g. llama3.2-vision vs llama3.2-vision:latest)
                return any(target in name or name in target for name in installed_names)
        except Exception:
            return False

    def assess_relevance(
        self,
        query: str,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> CitizenEvidenceAssessment:
        """Evaluate whether attached image is visually relevant to reported civic issue."""
        now = datetime.now(timezone.utc)
        clean_query = query.strip() if query else "Civic issue"

        # 1. Modality check: Must be an image
        if not (content_type.startswith("image/") or filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))):
            return CitizenEvidenceAssessment(
                relevance=EvidenceRelevanceOutcome.UNCERTAIN,
                reason="Non-image file modality; visual relevance assessment requires an image artifact.",
                detected_features=["unsupported_modality"],
                confidence=None,
                model_id=self.vision_model,
                ai_available=False,
                timestamp=now,
            )

        # 2. Check if configured model is text-only
        if not is_multimodal_vision_model(self.vision_model):
            return CitizenEvidenceAssessment(
                relevance=EvidenceRelevanceOutcome.UNCERTAIN,
                reason=f"VISION_MODEL_REQUIRED: Configured model '{self.vision_model}' is text-only and does not support image analysis.",
                detected_features=["text_only_model"],
                confidence=None,
                model_id=self.vision_model,
                ai_available=False,
                timestamp=now,
            )

        # 3. Check if test caller hook is provided
        if self._custom_caller is not None:
            try:
                res_dict = self._custom_caller({
                    "query": clean_query,
                    "filename": filename,
                    "content_type": content_type,
                    "file_bytes": file_bytes,
                })
                return self._parse_and_validate_response(res_dict, now)
            except Exception as exc:
                logger.warning("Custom vision caller failed: %s", exc)
                return CitizenEvidenceAssessment(
                    relevance=EvidenceRelevanceOutcome.UNCERTAIN,
                    reason=f"Vision inference failed: {exc}",
                    detected_features=["caller_failure"],
                    confidence=None,
                    model_id=self.vision_model,
                    ai_available=False,
                    timestamp=now,
                )

        # 4. Check if Ollama runtime and vision model are genuinely available
        if not self.is_model_available():
            return CitizenEvidenceAssessment(
                relevance=EvidenceRelevanceOutcome.UNCERTAIN,
                reason=f"Vision model '{self.vision_model}' is offline or unavailable; defaulting safely to UNCERTAIN.",
                detected_features=["model_unavailable"],
                confidence=None,
                model_id=self.vision_model,
                ai_available=False,
                timestamp=now,
            )

        # 5. Build task-specific multimodal prompt (Rule 8)
        prompt = (
            f"REPORTED CIVIC ISSUE:\n{clean_query}\n\n"
            f"TASK:\n"
            f"Determine whether the attached image is visually relevant to the reported civic issue.\n"
            f"Consider whether the image contains visual evidence related to the reported issue.\n\n"
            f"Return exactly one of:\n"
            f"RELATED\n"
            f"NOT_RELATED\n"
            f"UNCERTAIN\n\n"
            f"Do not determine whether the complaint is legally valid.\n"
            f"Do not determine department assignment.\n"
            f"Do not determine case resolution.\n"
            f"Do not make a lifecycle decision.\n\n"
            f"Respond ONLY with a JSON object with keys:\n"
            f"'relevance' (one of: RELATED, NOT_RELATED, UNCERTAIN),\n"
            f"'reason' (concise explanation up to 250 characters),\n"
            f"'detected_features' (list of observed features or elements),\n"
            f"'confidence' (float 0.0 to 1.0 or null)."
        )

        b64_image = base64.b64encode(file_bytes).decode("ascii")
        req_dict = {
            "model": self.vision_model,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
            "format": "json",
        }

        try:
            payload = json.dumps(req_dict).encode("utf-8")
            req = urllib.request.Request(
                f"{self.endpoint_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "{}")
                parsed = json.loads(response_text)
                return self._parse_and_validate_response(parsed, now)
        except urllib.error.URLError as err:
            logger.warning("Vision AI inference network failure: %s", err)
            return CitizenEvidenceAssessment(
                relevance=EvidenceRelevanceOutcome.UNCERTAIN,
                reason="Vision AI inference network timeout or error; defaulting to UNCERTAIN.",
                detected_features=["network_error"],
                confidence=None,
                model_id=self.vision_model,
                ai_available=False,
                timestamp=now,
            )
        except Exception as exc:
            logger.warning("Vision AI evaluation error: %s", exc)
            return CitizenEvidenceAssessment(
                relevance=EvidenceRelevanceOutcome.UNCERTAIN,
                reason=f"Vision evaluation error: {str(exc)[:150]}; defaulting to UNCERTAIN.",
                detected_features=["evaluation_error"],
                confidence=None,
                model_id=self.vision_model,
                ai_available=False,
                timestamp=now,
            )

    def _parse_and_validate_response(
        self,
        parsed: Dict[str, Any],
        now: datetime,
    ) -> CitizenEvidenceAssessment:
        """Validate and sanitize structured response from vision model."""
        raw_relevance = str(parsed.get("relevance", "UNCERTAIN")).strip().upper()
        if raw_relevance == "RELATED":
            relevance = EvidenceRelevanceOutcome.RELATED
        elif raw_relevance == "NOT_RELATED":
            relevance = EvidenceRelevanceOutcome.NOT_RELATED
        else:
            relevance = EvidenceRelevanceOutcome.UNCERTAIN

        raw_reason = str(parsed.get("reason", "")).strip()
        if not raw_reason:
            raw_reason = f"Image classified as {relevance.value} by vision assessment."

        raw_features = parsed.get("detected_features", [])
        if not isinstance(raw_features, list):
            raw_features = []
        clean_features = [str(f).strip() for f in raw_features if f and str(f).strip()]

        raw_conf = parsed.get("confidence")
        clean_conf: Optional[float] = None
        if raw_conf is not None:
            try:
                val = float(raw_conf)
                if 0.0 <= val <= 1.0:
                    clean_conf = round(val, 2)
            except (ValueError, TypeError):
                clean_conf = None

        return CitizenEvidenceAssessment(
            relevance=relevance,
            reason=raw_reason,
            detected_features=clean_features,
            confidence=clean_conf,
            model_id=self.vision_model,
            ai_available=True,
            timestamp=now,
        )


citizen_evidence_vision_service = CitizenEvidenceVisionService()
