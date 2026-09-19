"""Notification Worker Dispatcher for JARVIS Civic Phase 8.5.

Routes notification work items according to NOTIFICATION_EXECUTION_MODE:
- "DIRECT": Directly delegates to NotificationService (Phase 8.4 synchronous behavior).
- "SAM_LOCAL": Formats canonical NotificationWorkEvent and triggers serverless execution.

Preserves backend authority: All case details, recipients, and departments are sourced
strictly from persistent backend state (CaseStore/AccountRepository).
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional
import uuid

from app.config.settings import settings
from app.models.notification import NotificationRecord
from app.models.security import CivicCaseRecord, EvidenceMetadata
from app.models.worker_event import (
    NotificationWorkEvent,
    WorkerEventType,
    WorkerExecutionStatus,
    WorkerResponse,
)
from app.services.case_store import case_store
from app.services.notifications.notification_service import (
    NotificationService,
    notification_service,
)

logger = logging.getLogger("jarvis.notifications.dispatcher")


class NotificationWorkerDispatcher:
    """Dispatches notification work items based on configuration mode."""

    def __init__(
        self,
        notif_service: Optional[NotificationService] = None,
        sam_executable: Optional[str] = None,
    ):
        self._notif_service = notif_service or notification_service
        self._sam_executable = sam_executable

    def _resolve_sam_cmd(self) -> Optional[str]:
        """Locate SAM CLI executable on system."""
        if self._sam_executable and os.path.exists(self._sam_executable):
            return self._sam_executable
        cmd = shutil.which("sam")
        if cmd:
            return cmd
        # Check active python virtual environment Scripts directory
        import sys
        venv_sam = os.path.join(os.path.dirname(sys.executable), "sam.exe")
        if os.path.exists(venv_sam):
            return venv_sam
        # Standard Windows installation path for Amazon.SAM-CLI
        win_path = r"C:\Program Files\Amazon\AWSSAMCLI\bin\sam.exe"
        if os.path.exists(win_path):
            return win_path
        return None

    def create_work_event(
        self,
        case_id: str,
        event_type: WorkerEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> NotificationWorkEvent:
        """Construct canonical NotificationWorkEvent."""
        eid = event_id or f"evt-{uuid.uuid4().hex[:12]}"
        return NotificationWorkEvent(
            event_id=eid,
            event_type=event_type,
            case_id=case_id,
            event_version=1,
            payload=payload or {},
        )

    def dispatch_case_created(self, case: CivicCaseRecord) -> List[NotificationRecord]:
        """Dispatch case created notification via configured execution mode."""
        if settings.NOTIFICATION_EXECUTION_MODE == "SAM_LOCAL":
            event = self.create_work_event(
                case_id=case.case_id,
                event_type=WorkerEventType.CASE_CREATED,
            )
            resp = self.invoke_sam_local(event)
            logger.info("SAM_LOCAL dispatch_case_created response: %s", resp.status)
            return self._notif_service.get_case_notifications(case.case_id)
        return self._notif_service.dispatch_case_created(case)

    def dispatch_workflow_stage_changed(
        self,
        case: CivicCaseRecord,
        previous_status: str,
        new_status: str,
    ) -> List[NotificationRecord]:
        """Dispatch workflow stage change notification via configured execution mode."""
        if settings.NOTIFICATION_EXECUTION_MODE == "SAM_LOCAL":
            event = self.create_work_event(
                case_id=case.case_id,
                event_type=WorkerEventType.WORKFLOW_STAGE_CHANGED,
                payload={"previous_status": previous_status, "new_status": new_status},
            )
            resp = self.invoke_sam_local(event)
            logger.info("SAM_LOCAL dispatch_workflow_stage_changed response: %s", resp.status)
            return self._notif_service.get_case_notifications(case.case_id)
        return self._notif_service.dispatch_stage_changed(
            case, previous_status, new_status
        )

    def dispatch_evidence_uploaded(
        self,
        case: CivicCaseRecord,
        evidence_metadata: EvidenceMetadata,
    ) -> List[NotificationRecord]:
        """Dispatch evidence uploaded notification via configured execution mode."""
        if settings.NOTIFICATION_EXECUTION_MODE == "SAM_LOCAL":
            event = self.create_work_event(
                case_id=case.case_id,
                event_type=WorkerEventType.EVIDENCE_AVAILABLE,
                payload={"file_id": evidence_metadata.file_id, "file_name": evidence_metadata.file_name},
            )
            resp = self.invoke_sam_local(event)
            logger.info("SAM_LOCAL dispatch_evidence_uploaded response: %s", resp.status)
            return self._notif_service.get_case_notifications(case.case_id)
        return self._notif_service.dispatch_evidence_available(case, evidence_metadata)

    def dispatch_resolution_ready(
        self,
        case: CivicCaseRecord,
        proposed_notes: Optional[str] = None,
    ) -> List[NotificationRecord]:
        """Dispatch proposed resolution notification via configured execution mode."""
        if settings.NOTIFICATION_EXECUTION_MODE == "SAM_LOCAL":
            event = self.create_work_event(
                case_id=case.case_id,
                event_type=WorkerEventType.RESOLUTION_READY,
                payload={"proposed_notes": proposed_notes},
            )
            resp = self.invoke_sam_local(event)
            logger.info("SAM_LOCAL dispatch_resolution_ready response: %s", resp.status)
            return self._notif_service.get_case_notifications(case.case_id)
        return self._notif_service.dispatch_resolution_ready(case, proposed_notes)

    @staticmethod
    def sync_backend_packaging() -> None:
        """Synchronize authoritative backend/app code into sam/src/notification_worker/backend/app.

        Guarantees the containerized SAM execution layer uses the exact authoritative backend
        business logic without manual synchronization or silent divergence.
        """
        import shutil
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_app = os.path.abspath(os.path.join(current_dir, "../.."))
        worker_target = os.path.abspath(
            os.path.join(current_dir, "../../../../sam/src/notification_worker/backend/app")
        )
        if not os.path.exists(backend_app) or not os.path.exists(os.path.dirname(worker_target)):
            return
        os.makedirs(worker_target, exist_ok=True)
        for root, _, files in os.walk(backend_app):
            if "__pycache__" in root or ".pytest_cache" in root:
                continue
            rel = os.path.relpath(root, backend_app)
            dest_dir = os.path.join(worker_target, rel) if rel != "." else worker_target
            os.makedirs(dest_dir, exist_ok=True)
            for f in files:
                if f.endswith(".pyc"):
                    continue
                s_file = os.path.join(root, f)
                d_file = os.path.join(dest_dir, f)
                if not os.path.exists(d_file) or os.path.getmtime(s_file) > os.path.getmtime(d_file):
                    shutil.copy2(s_file, d_file)

    def invoke_sam_local(
        self,
        event: NotificationWorkEvent,
        template_path: str = "sam/template.yaml",
        function_identifier: str = "NotificationWorkerFunction",
        timeout_seconds: int = 60,
    ) -> WorkerResponse:
        """Execute real AWS SAM CLI local invoke using the compiled template and event.

        Distinguishes real SAM CLI execution from direct python calls.
        """
        # Ensure packaging mirror is in 100% sync before container execution
        self.sync_backend_packaging()

        sam_bin = self._resolve_sam_cmd()
        if not sam_bin:
            logger.error("SAM CLI binary not found in PATH or standard install location")
            return WorkerResponse(
                status=WorkerExecutionStatus.FAILED,
                event_id=event.event_id,
                case_id=event.case_id,
                reason="SAM_CLI_NOT_INSTALLED",
                errors=["AWS SAM CLI binary was not found on the host system."],
            )

        # Write event to a temporary JSON file for SAM invocation
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump(event.model_dump(), tf)
            temp_event_file = tf.name

        try:
            cmd = [
                sam_bin,
                "local",
                "invoke",
                function_identifier,
                "--template",
                template_path,
                "--event",
                temp_event_file,
            ]
            logger.info("Executing real SAM CLI invoke: %s", " ".join(cmd))
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            if proc.returncode != 0:
                logger.error("SAM CLI local invoke failed (code %d): %s", proc.returncode, proc.stderr)
                return WorkerResponse(
                    status=WorkerExecutionStatus.FAILED,
                    event_id=event.event_id,
                    case_id=event.case_id,
                    reason="SAM_CLI_INVOKE_ERROR",
                    errors=[proc.stderr.strip() or f"Exit code {proc.returncode}"],
                )

            # Parse Lambda response from stdout
            # SAM CLI prints logs to stderr/stdout; the return payload is typically the last JSON block
            raw_output = proc.stdout.strip()
            parsed_payload = self._extract_json_payload(raw_output)
            if parsed_payload:
                return WorkerResponse(**parsed_payload)

            return WorkerResponse(
                status=WorkerExecutionStatus.SENT,
                event_id=event.event_id,
                case_id=event.case_id,
                message="SAM invocation completed successfully",
            )
        except subprocess.TimeoutExpired:
            logger.error("SAM CLI local invoke timed out after %d seconds", timeout_seconds)
            return WorkerResponse(
                status=WorkerExecutionStatus.FAILED,
                event_id=event.event_id,
                case_id=event.case_id,
                reason="TIMEOUT",
                errors=[f"SAM invocation timed out after {timeout_seconds}s"],
            )
        except Exception as ex:
            logger.error("Unexpected error invoking SAM CLI: %s", ex)
            return WorkerResponse(
                status=WorkerExecutionStatus.FAILED,
                event_id=event.event_id,
                case_id=event.case_id,
                reason="INVOCATION_EXCEPTION",
                errors=[str(ex)],
            )
        finally:
            if os.path.exists(temp_event_file):
                try:
                    os.remove(temp_event_file)
                except OSError:
                    pass

    def _extract_json_payload(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract the last valid JSON object from command output."""
        lines = text.strip().splitlines()
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except Exception:
                    pass
        # Try finding multi-line JSON if single line fails
        try:
            start = text.rfind("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            pass
        return None


worker_dispatcher = NotificationWorkerDispatcher()
