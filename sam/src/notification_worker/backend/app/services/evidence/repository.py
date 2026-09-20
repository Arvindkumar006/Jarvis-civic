"""Thread-Safe Durable Evidence Verification Repository for JARVIS Civic.

Phase 8.7: Durable store for trusted server-side EvidenceRecord
and EvidenceVerificationRecord instances. Survives backend restarts.
"""

from datetime import datetime, timezone
import json
import logging
import os
import threading
from typing import Dict, List, Optional

from app.models.evidence import EvidenceRecord, EvidenceVerificationRecord

logger = logging.getLogger("jarvis.evidence.repository")


class EvidenceVerificationRepository:
    """Thread-safe durable storage for evidence records and verification records."""

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path:
            self._storage_path = storage_path
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            data_dir = os.path.join(base_dir, ".data")
            self._storage_path = os.getenv("EVIDENCE_STORE_PATH", os.path.join(data_dir, "evidence_store.json"))

        self._evidence: Dict[str, EvidenceRecord] = {}  # evidence_id -> EvidenceRecord
        self._case_evidence: Dict[str, List[str]] = {}  # case_id -> [evidence_id, ...]
        self._verifications: Dict[str, EvidenceVerificationRecord] = {}  # verification_id -> Record
        self._evidence_to_verification: Dict[str, str] = {}  # evidence_id -> verification_id
        self._lock = threading.Lock()

        # Initialize storage directory and load existing persisted records
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            self._load_from_disk()
        except Exception as err:
            logger.warning("Could not initialize durable evidence storage at %s: %s", self._storage_path, err)

    def _save_to_disk(self) -> None:
        """Atomically persist records to durable JSON file."""
        try:
            parent = os.path.dirname(self._storage_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            data = {
                "evidence": {eid: rec.model_dump(mode="json") for eid, rec in self._evidence.items()},
                "verifications": {vid: ver.model_dump(mode="json") for vid, ver in self._verifications.items()},
                "case_evidence": self._case_evidence,
                "evidence_to_verification": self._evidence_to_verification,
            }

            tmp_path = f"{self._storage_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            try:
                os.replace(tmp_path, self._storage_path)
            except OSError:
                import shutil
                shutil.copyfile(tmp_path, self._storage_path)
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        except Exception as err:
            logger.error("Failed to persist evidence store to disk: %s", err)

    def _load_from_disk(self) -> None:
        """Load persisted evidence and verification records from disk."""
        if not os.path.exists(self._storage_path):
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            evidence_map = {}
            for eid, item in data.get("evidence", {}).items():
                try:
                    evidence_map[eid] = EvidenceRecord.model_validate(item)
                except Exception as parse_err:
                    logger.warning("Skipping malformed evidence item %s: %s", eid, parse_err)

            verifications_map = {}
            for vid, item in data.get("verifications", {}).items():
                try:
                    verifications_map[vid] = EvidenceVerificationRecord.model_validate(item)
                except Exception as parse_err:
                    logger.warning("Skipping malformed verification item %s: %s", vid, parse_err)

            self._evidence = evidence_map
            self._verifications = verifications_map
            self._case_evidence = data.get("case_evidence", {})
            self._evidence_to_verification = data.get("evidence_to_verification", {})

            logger.info(
                "Loaded %d evidence records and %d verification records from %s",
                len(self._evidence),
                len(self._verifications),
                self._storage_path,
            )
        except Exception as err:
            logger.error("Failed to load evidence records from disk: %s", err)

    def save_evidence(self, record: EvidenceRecord) -> EvidenceRecord:
        """Persist trusted evidence record."""
        with self._lock:
            self._evidence[record.evidence_id] = record
            if record.case_id not in self._case_evidence:
                self._case_evidence[record.case_id] = []
            if record.evidence_id not in self._case_evidence[record.case_id]:
                self._case_evidence[record.case_id].append(record.evidence_id)
            self._save_to_disk()
            return record

    def get_evidence(self, case_id: str, evidence_id: str) -> Optional[EvidenceRecord]:
        """Retrieve evidence record if it exists and belongs to the given case."""
        with self._lock:
            record = self._evidence.get(evidence_id)
            if record and record.case_id == case_id:
                return record
            return None

    def list_evidence_for_case(self, case_id: str) -> List[EvidenceRecord]:
        """List all evidence records for a case."""
        with self._lock:
            ids = self._case_evidence.get(case_id, [])
            return [self._evidence[eid] for eid in ids if eid in self._evidence]

    def save_verification(self, record: EvidenceVerificationRecord) -> EvidenceVerificationRecord:
        """Persist verification evaluation record."""
        with self._lock:
            self._verifications[record.verification_id] = record
            self._evidence_to_verification[record.evidence_id] = record.verification_id
            self._save_to_disk()
            return record

    def get_verification_for_evidence(self, evidence_id: str) -> Optional[EvidenceVerificationRecord]:
        """Retrieve verification record for an evidence artifact."""
        with self._lock:
            vid = self._evidence_to_verification.get(evidence_id)
            if vid:
                return self._verifications.get(vid)
            return None

    def clear(self) -> None:
        """Clear all stored evidence and verification records (testing helper)."""
        with self._lock:
            self._evidence.clear()
            self._case_evidence.clear()
            self._verifications.clear()
            self._evidence_to_verification.clear()
            if os.path.exists(self._storage_path):
                try:
                    os.remove(self._storage_path)
                except Exception:
                    pass


# Global singleton instance
evidence_repo = EvidenceVerificationRepository()
