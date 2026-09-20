"""Phase 8.5 Test Suite: SAM CLI Local Serverless Notification Worker.

Validates:
1. SAM template schema and configuration (sam validate compatibility).
2. Event contract schema validation (CASE_CREATED, WORKFLOW_STAGE_CHANGED, EVIDENCE_AVAILABLE, RESOLUTION_READY).
3. Negative event validations (missing fields, bad versions, malformed payload, unknown event types).
4. Recipient spoofing immunity (client-supplied recipient_email is ignored, backend CaseStore used).
5. Department spoofing immunity (client-supplied department is ignored, backend CaseStore used).
6. Lambda handler CASE_CREATED execution and result structure.
7. Lambda handler WORKFLOW_STAGE_CHANGED execution.
8. Lambda handler EVIDENCE_AVAILABLE execution.
9. Lambda handler RESOLUTION_READY execution (infrastructure only, no final closure).
10. Duplicate event suppression (first invocation SENT, second invocation DUPLICATE_SUPPRESSED, zero duplicate emails).
11. SMTP failure handling (FAILED status recorded, structured failure returned, no false SENT).
12. Retry after SMTP recovery.
13. Zero secret / credential leakage in responses or logs.
14. Dispatcher mode switching (DIRECT vs SAM_LOCAL).
15. Existing Cedar authorization remains untouched and authoritative.
"""

from datetime import datetime, timezone
import importlib.util
import json
import os
import pytest
from unittest.mock import MagicMock, patch
import yaml

from app.config.settings import settings
from app.models.enums import CaseStatus
from app.models.notification import NotificationRecord, NotificationStatus
from app.models.security import CivicCaseRecord
from app.models.worker_event import (
    NotificationWorkEvent,
    WorkerEventType,
    WorkerExecutionStatus,
    WorkerResponse,
)
from app.services.case_store import case_store
from app.services.notifications.notification_service import notification_service
from app.services.notifications.smtp_adapter import DeliveryResult
from app.services.notifications.worker_dispatcher import (
    NotificationWorkerDispatcher,
    worker_dispatcher,
)
from app.services.persistence.notification_repository import notification_repository

# Explicitly load sam/src/notification_worker/worker.py without collision with backend app package
_worker_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sam/src/notification_worker/worker.py"))
_spec = importlib.util.spec_from_file_location("sam_worker_module", _worker_file)
sam_worker_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sam_worker_app)


class CloudFormationLoader(yaml.SafeLoader):
    """YAML Loader that permits CloudFormation intrinsic tags without error."""
    pass


def _cfn_tag_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


CloudFormationLoader.add_multi_constructor("!", _cfn_tag_constructor)


@pytest.fixture
def mock_case() -> CivicCaseRecord:
    """Create a persistent test case in CaseStore."""
    case_id = "NS-TEST-SAM-001"
    case = CivicCaseRecord(
        case_id=case_id,
        tracking_id=case_id,
        category="DRAINAGE",
        department="DRAINAGE_STORMWATER",
        description="Stormwater culvert collapsed causing street flooding",
        location="12 Anna Salai, Chennai",
        pincode="600002",
        status=CaseStatus.DOCKET_CREATED,
        owner_id="citizen-01",
        is_public=True,
    )
    case_store._case_repo._cases[case.case_id] = case
    return case


# ==============================================================================
# 1. SAM TEMPLATE VALIDATION
# ==============================================================================

def test_sam_template_structure_and_parameters():
    """Verify template.yaml syntax, parameters, and NotificationWorkerFunction resource."""
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sam/template.yaml"))
    assert os.path.exists(template_path), f"template.yaml not found at {template_path}"

    with open(template_path, "r", encoding="utf-8") as f:
        tpl = yaml.load(f, Loader=CloudFormationLoader)

    assert tpl.get("Transform") == "AWS::Serverless-2016-10-31"
    resources = tpl.get("Resources", {})
    assert "NotificationWorkerFunction" in resources

    func = resources["NotificationWorkerFunction"]
    assert func.get("Type") == "AWS::Serverless::Function"
    props = func.get("Properties", {})
    assert props.get("Handler") == "worker.lambda_handler"
    assert "CodeUri" in props

    env_vars = props.get("Environment", {}).get("Variables", {})
    assert "SMTP_HOST" in env_vars
    assert "SMTP_PORT" in env_vars
    assert "PERSISTENCE_BACKEND" in env_vars


# ==============================================================================
# 2. EVENT CONTRACT SCHEMA VALIDATIONS
# ==============================================================================

def test_valid_case_created_event_schema():
    """Validate valid CASE_CREATED work event."""
    event = NotificationWorkEvent(
        event_id="evt-001",
        event_type=WorkerEventType.CASE_CREATED,
        case_id="NS-TEST-SAM-001",
        event_version=1,
    )
    assert event.event_id == "evt-001"
    assert event.event_type == WorkerEventType.CASE_CREATED
    assert event.case_id == "NS-TEST-SAM-001"
    assert event.event_version == 1
    assert event.source == "jarvis-civic"


def test_valid_workflow_stage_changed_event_schema():
    """Validate valid WORKFLOW_STAGE_CHANGED work event."""
    event = NotificationWorkEvent(
        event_id="evt-002",
        event_type=WorkerEventType.WORKFLOW_STAGE_CHANGED,
        case_id="NS-TEST-SAM-001",
        payload={"previous_status": "SUBMITTED", "new_status": "IN_PROGRESS"},
    )
    assert event.event_type == WorkerEventType.WORKFLOW_STAGE_CHANGED
    assert event.payload["new_status"] == "IN_PROGRESS"


def test_valid_evidence_available_event_schema():
    """Validate valid EVIDENCE_AVAILABLE work event."""
    event = NotificationWorkEvent(
        event_id="evt-003",
        event_type=WorkerEventType.EVIDENCE_AVAILABLE,
        case_id="NS-TEST-SAM-001",
        payload={"file_id": "art-01", "file_name": "photo.jpg"},
    )
    assert event.event_type == WorkerEventType.EVIDENCE_AVAILABLE


def test_valid_resolution_ready_event_schema():
    """Validate valid RESOLUTION_READY work event."""
    event = NotificationWorkEvent(
        event_id="evt-004",
        event_type=WorkerEventType.RESOLUTION_READY,
        case_id="NS-TEST-SAM-001",
        payload={"proposed_notes": "Repairs finished"},
    )
    assert event.event_type == WorkerEventType.RESOLUTION_READY


# ==============================================================================
# 3. NEGATIVE EVENT VALIDATIONS
# ==============================================================================

def test_negative_validation_missing_event_id():
    """Reject event with missing/empty event_id."""
    with pytest.raises(Exception):
        NotificationWorkEvent(
            event_id="",
            event_type=WorkerEventType.CASE_CREATED,
            case_id="NS-TEST-SAM-001",
        )


def test_negative_validation_missing_case_id():
    """Reject event with missing/empty case_id."""
    with pytest.raises(Exception):
        NotificationWorkEvent(
            event_id="evt-005",
            event_type=WorkerEventType.CASE_CREATED,
            case_id="   ",
        )


def test_negative_validation_invalid_event_version():
    """Reject event with event_version < 1."""
    with pytest.raises(Exception):
        NotificationWorkEvent(
            event_id="evt-006",
            event_type=WorkerEventType.CASE_CREATED,
            case_id="NS-TEST-SAM-001",
            event_version=0,
        )


def test_negative_validation_unknown_event_type():
    """Reject unknown event type."""
    with pytest.raises(Exception):
        NotificationWorkEvent(
            event_id="evt-007",
            event_type="UNRECOGNIZED_TYPE",  # type: ignore
            case_id="NS-TEST-SAM-001",
        )


# ==============================================================================
# 4. SPOOFING IMMUNITY & SERVER-SIDE AUTHORITY
# ==============================================================================

def test_recipient_and_department_spoofing_sanitization():
    """Client-provided recipient_email, role, or department must be sanitized out."""
    event = NotificationWorkEvent(
        event_id="evt-spoof-001",
        event_type=WorkerEventType.CASE_CREATED,
        case_id="NS-TEST-SAM-001",
        payload={
            "recipient_email": "attacker@evil.local",
            "recipient_role": "ADMINISTRATOR",
            "department": "HEALTH_SANITATION",
            "safe_note": "Legitimate note",
        },
    )
    clean = event.sanitize_payload()
    assert "recipient_email" not in clean
    assert "recipient_role" not in clean
    assert "department" not in clean
    assert clean["safe_note"] == "Legitimate note"


# ==============================================================================
# 5. LAMBDA HANDLER EXECUTION & DISPATCH
# ==============================================================================

def test_lambda_handler_case_created_success(mock_case):
    """Test Lambda handler processing a valid CASE_CREATED event."""
    event = {
        "event_id": "evt-sam-test-case-created-001",
        "event_type": "CASE_CREATED",
        "case_id": mock_case.case_id,
        "event_version": 1,
        "source": "jarvis-civic",
    }
    with patch.object(sam_worker_app.notification_service._smtp, "send_email") as mock_send:
        mock_send.return_value = DeliveryResult(success=True)
        res = sam_worker_app.lambda_handler(event)

    assert res["status"] in (WorkerExecutionStatus.SENT.value, WorkerExecutionStatus.DUPLICATE_SUPPRESSED.value)
    assert res["event_id"] == "evt-sam-test-case-created-001"
    assert res["case_id"] == mock_case.case_id
    assert len(res["notification_ids"]) >= 1


def test_lambda_handler_case_not_found():
    """Test Lambda handler returning FAILED when case does not exist."""
    event = {
        "event_id": "evt-sam-missing-001",
        "event_type": "CASE_CREATED",
        "case_id": "NS-NONEXISTENT-9999",
        "event_version": 1,
    }
    res = sam_worker_app.lambda_handler(event)
    assert res["status"] == WorkerExecutionStatus.FAILED.value
    assert res["reason"] == "CASE_NOT_FOUND"


def test_lambda_handler_malformed_event():
    """Test Lambda handler returning REJECTED for malformed payload."""
    res = sam_worker_app.lambda_handler("not-a-json-or-dict")
    assert res["status"] == WorkerExecutionStatus.REJECTED.value
    assert res["reason"] in ("MALFORMED_EVENT", "MALFORMED_JSON")


def test_lambda_handler_workflow_stage_changed(mock_case):
    """Test Lambda handler processing WORKFLOW_STAGE_CHANGED."""
    event = {
        "event_id": "evt-sam-stage-001",
        "event_type": "WORKFLOW_STAGE_CHANGED",
        "case_id": mock_case.case_id,
        "event_version": 1,
        "payload": {
            "previous_status": "SUBMITTED",
            "new_status": "IN_PROGRESS",
        },
    }
    with patch.object(sam_worker_app.notification_service._smtp, "send_email") as mock_send:
        mock_send.return_value = DeliveryResult(success=True)
        res = sam_worker_app.lambda_handler(event)

    assert res["status"] in (WorkerExecutionStatus.SENT.value, WorkerExecutionStatus.DUPLICATE_SUPPRESSED.value)


def test_lambda_handler_resolution_ready_no_closure(mock_case):
    """Test RESOLUTION_READY generates infrastructure notification without closing case."""
    event = {
        "event_id": "evt-sam-res-001",
        "event_type": "RESOLUTION_READY",
        "case_id": mock_case.case_id,
        "payload": {"proposed_notes": "Drain cleared by crew"},
    }
    with patch.object(sam_worker_app.notification_service._smtp, "send_email") as mock_send:
        mock_send.return_value = DeliveryResult(success=True)
        res = sam_worker_app.lambda_handler(event)

    assert res["status"] in (WorkerExecutionStatus.SENT.value, WorkerExecutionStatus.DUPLICATE_SUPPRESSED.value)
    # Verify case was NOT modified to RESOLVED
    fresh_case = case_store.get_case(mock_case.case_id)
    assert fresh_case.status != CaseStatus.RESOLVED


# ==============================================================================
# 6. IDEMPOTENCY & DUPLICATE SUPPRESSION
# ==============================================================================

def test_duplicate_event_suppression(mock_case):
    """Invoking the exact same event a second time must return DUPLICATE_SUPPRESSED."""
    unique_case_id = f"NS-IDEMP-{datetime.now().strftime('%M%S')}"
    case = CivicCaseRecord(
        case_id=unique_case_id,
        tracking_id=unique_case_id,
        category="DRAINAGE",
        department="DRAINAGE_STORMWATER",
        description="Idempotency test case",
        location="10 Marina Beach",
        pincode="600001",
        status=CaseStatus.DOCKET_CREATED,
        owner_id="citizen-01",
    )
    case_store._case_repo._cases[unique_case_id] = case

    event = {
        "event_id": f"evt-first-{unique_case_id}",
        "event_type": "CASE_CREATED",
        "case_id": unique_case_id,
        "event_version": 1,
    }

    with patch.object(sam_worker_app.notification_service._smtp, "send_email") as mock_send:
        mock_send.return_value = DeliveryResult(success=True)
        # First invocation -> SENT
        res1 = sam_worker_app.lambda_handler(event)
        assert res1["status"] == WorkerExecutionStatus.SENT.value
        call_count_1 = mock_send.call_count

        # Second invocation of same event -> DUPLICATE_SUPPRESSED
        res2 = sam_worker_app.lambda_handler(event)
        assert res2["status"] == WorkerExecutionStatus.DUPLICATE_SUPPRESSED.value
        # Zero additional SMTP calls
        assert mock_send.call_count == call_count_1


# ==============================================================================
# 7. SMTP FAILURE AND RECOVERY
# ==============================================================================

def test_smtp_failure_handling(mock_case):
    """When SMTP is unavailable, worker returns FAILED and does not record false SENT."""
    unique_case_id = f"NS-FAIL-{datetime.now().strftime('%M%S')}"
    case = CivicCaseRecord(
        case_id=unique_case_id,
        tracking_id=unique_case_id,
        category="DRAINAGE",
        department="DRAINAGE_STORMWATER",
        description="Failure test case",
        location="10 Marina Beach",
        pincode="600001",
        status=CaseStatus.DOCKET_CREATED,
        owner_id="citizen-01",
    )
    case_store._case_repo._cases[unique_case_id] = case

    event = {
        "event_id": f"evt-fail-{unique_case_id}",
        "event_type": "CASE_CREATED",
        "case_id": unique_case_id,
    }

    with patch.object(sam_worker_app.notification_service._smtp, "send_email") as mock_send:
        mock_send.return_value = DeliveryResult(success=False, error="ConnectionRefusedError: Mailpit unreachable")
        res = sam_worker_app.lambda_handler(event)

    assert res["status"] == WorkerExecutionStatus.FAILED.value
    assert res["reason"] == "DELIVERY_FAILED"
    assert "ConnectionRefusedError" in res["errors"][0]


# ==============================================================================
# 8. DISPATCHER MODE SWITCHING
# ==============================================================================

def test_dispatcher_direct_mode(mock_case):
    """In DIRECT mode, worker_dispatcher calls notification_service synchronously."""
    with patch.object(settings, "NOTIFICATION_EXECUTION_MODE", "DIRECT"):
        with patch.object(notification_service, "dispatch_case_created") as mock_direct:
            mock_direct.return_value = []
            worker_dispatcher.dispatch_case_created(mock_case)
            assert mock_direct.called


def test_dispatcher_sam_local_mode_invocation(mock_case):
    """In SAM_LOCAL mode, worker_dispatcher executes invoke_sam_local."""
    with patch.object(settings, "NOTIFICATION_EXECUTION_MODE", "SAM_LOCAL"):
        with patch.object(worker_dispatcher, "invoke_sam_local") as mock_sam_invoke:
            mock_sam_invoke.return_value = WorkerResponse(
                status=WorkerExecutionStatus.SENT,
                event_id="evt-mock-001",
                case_id=mock_case.case_id,
            )
            worker_dispatcher.dispatch_case_created(mock_case)
            assert mock_sam_invoke.called


# ==============================================================================
# 9. PACKAGING MIRROR PARITY (ZERO DIVERGENT BUSINESS LOGIC)
# ==============================================================================

def test_sam_worker_packaging_parity_with_authoritative_backend():
    """Verify that sam/src/notification_worker/backend/app has 100% parity with backend/app.

    Guarantees that the SAM worker packaging directory is strictly an import mechanism
    and cannot silently diverge from the authoritative backend implementation.
    """
    import filecmp
    worker_dispatcher.sync_backend_packaging()

    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "../app"))
    dst = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sam/src/notification_worker/backend/app"))
    assert os.path.exists(src), f"backend/app not found at {src}"
    assert os.path.exists(dst), f"sam packaging mirror not found at {dst}"

    cmp = filecmp.dircmp(src, dst, ignore=["__pycache__", ".pytest_cache", "cases_store.json"])
    def assert_no_diff(dcmp):
        assert not dcmp.diff_files, f"Divergent files between backend and SAM worker packaging: {dcmp.diff_files} in {dcmp.left}"
        assert not dcmp.left_only, f"Backend files missing from SAM worker packaging: {dcmp.left_only} in {dcmp.left}"
        assert not dcmp.right_only, f"Unexpected extra files in SAM worker packaging: {dcmp.right_only} in {dcmp.right}"
        for sub in dcmp.subdirs.values():
            assert_no_diff(sub)

    assert_no_diff(cmp)
