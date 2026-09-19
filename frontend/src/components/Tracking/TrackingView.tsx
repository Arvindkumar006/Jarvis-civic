import React, { useState, useEffect, useMemo } from 'react';
import {
  Search,
  ShieldAlert,
  Building2,
  Clock,
  Check,
  Copy,
  Paperclip,
  ArrowRight,
  AlertCircle,
  MapPin,
  Lock,
  Globe,
  ShieldCheck,
  Sliders,
  AlertTriangle,
  FileCheck2,
  Send,
  ThumbsUp,
  ThumbsDown,
  CheckCircle2,
  XCircle,
  Info,
} from 'lucide-react';
import {
  ApplicationRole,
  AuditEvent,
  CaseHistoryItem,
  CaseStatus,
  CivicCaseRecord,
  CivicEvidenceType,
  ControlledDepartment,
  EvidenceResponse,
  PublicTrackingProjection,
} from '../../types/civic';
import { auditApi, casesApi, evidenceApi, trackingApi } from '../../services/api';
import { CivicMap, getApproxCoordinates, MapMarkerItem } from '../Map/CivicMap';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useAuth } from '../../context/AuthContext';
import './TrackingView.css';

interface TrackingViewProps {
  initialCaseId?: string;
  recentCaseIds?: string[];
  onSelectCaseForEvidence?: (caseId: string) => void;
  initialMode?: TrackingMode;
}

type TrackingMode = 'PUBLIC' | 'AUTHORITY' | 'AUDIT';

interface JourneyStep {
  step: number;
  label: string;
  code: CaseStatus;
  desc: string;
}

const CANONICAL_JOURNEY: JourneyStep[] = [
  { step: 1, label: 'Docket Created', code: CaseStatus.DOCKET_CREATED, desc: 'Civic grievance synthesized and structured into record.' },
  { step: 2, label: 'Routing Prepared', code: CaseStatus.ROUTING_PREPARED, desc: 'Routing prepared for the recommended department.' },
  { step: 3, label: 'Submission Ready', code: CaseStatus.SUBMISSION_READY, desc: 'Prepared for potential authority intake.' },
  { step: 4, label: 'Under Review', code: CaseStatus.UNDER_REVIEW, desc: 'Authority review and triage stage.' },
  { step: 5, label: 'Resolved', code: CaseStatus.RESOLVED, desc: 'Resolution recorded in the civic workflow.' },
];

const VALID_NEXT_TRANSITIONS: Record<
  CaseStatus,
  { nextStatus: CaseStatus; label: string; actionDesc: string } | null
> = {
  [CaseStatus.DRAFT]: {
    nextStatus: CaseStatus.DOCKET_CREATED,
    label: 'CREATE DOCKET',
    actionDesc: 'Formalize draft into an active civic action docket.',
  },
  [CaseStatus.DOCKET_CREATED]: {
    nextStatus: CaseStatus.ROUTING_PREPARED,
    label: 'PREPARE ROUTING',
    actionDesc: 'Confirm departmental jurisdiction and prepare routing docket.',
  },
  [CaseStatus.ROUTING_PREPARED]: {
    nextStatus: CaseStatus.SUBMISSION_READY,
    label: 'MARK SUBMISSION READY',
    actionDesc: 'Verify evidence checklist and certify docket for authority review.',
  },
  [CaseStatus.SUBMISSION_READY]: {
    nextStatus: CaseStatus.UNDER_REVIEW,
    label: 'COMMENCE REVIEW',
    actionDesc: 'Initiate formal departmental triage and municipal investigation.',
  },
  [CaseStatus.UNDER_REVIEW]: null, // GATED: Closure transitions directly via authenticated citizen resolution confirmation
  [CaseStatus.RESOLVED]: null,
};

export const TrackingView: React.FC<TrackingViewProps> = ({
  initialCaseId = '',
  recentCaseIds = [],
  onSelectCaseForEvidence,
  initialMode,
}) => {
  // Inherit active workspace & backend auth context
  const { session } = useWorkspace();
  let auth: ReturnType<typeof useAuth> | null = null;
  try {
    auth = useAuth();
  } catch {
    auth = null;
  }

  const effectiveRole = auth && auth.isAuthenticated ? auth.role : session.role;
  const effectiveDept = auth && auth.isAuthenticated ? auth.department : session.department;
  const effectivePid = auth && auth.isAuthenticated ? auth.principalId : session.principalId;
  const effectiveName = auth?.displayName || session.label;

  // Mode selection (PUBLIC, AUTHORITY, AUDIT)
  const [activeMode, setActiveMode] = useState<TrackingMode>(() => {
    if (initialMode) return initialMode;
    return 'PUBLIC';
  });

  // Sync mode if initialMode prop changes
  useEffect(() => {
    if (initialMode) {
      setActiveMode(initialMode);
    }
  }, [initialMode]);

  // Restrict mode if role changes
  useEffect(() => {
    if (effectiveRole === ApplicationRole.PUBLIC || effectiveRole === ApplicationRole.CITIZEN) {
      if (activeMode !== 'PUBLIC') setActiveMode('PUBLIC');
    } else if (effectiveRole === ApplicationRole.AUTHORITY_OFFICER && activeMode === 'AUDIT') {
      setActiveMode('AUTHORITY');
    }
  }, [effectiveRole, activeMode]);

  // Input & Query State
  const [caseIdInput, setCaseIdInput] = useState(initialCaseId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projection, setProjection] = useState<PublicTrackingProjection | null>(null);
  const [caseRecord, setCaseRecord] = useState<CivicCaseRecord | null>(null);
  const [copied, setCopied] = useState(false);

  // Authority Workflow State
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [transitionNote, setTransitionNote] = useState('');
  const [workflowActionLoading, setWorkflowActionLoading] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [workflowSuccessMsg, setWorkflowSuccessMsg] = useState<string | null>(null);

  // Resolution Note State
  const [newResolutionNote, setNewResolutionNote] = useState('');
  const [resolutionSubmitting, setResolutionSubmitting] = useState(false);

  // History & Audit State
  const [caseHistory, setCaseHistory] = useState<CaseHistoryItem[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditRestricted, setAuditRestricted] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);

  // Evidence & Citizen Resolution State
  const [caseEvidence, setCaseEvidence] = useState<EvidenceResponse[]>([]);
  const [acceptModalOpen, setAcceptModalOpen] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [citizenFeedback, setCitizenFeedback] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [resolutionActionLoading, setResolutionActionLoading] = useState(false);
  const [resolutionActionError, setResolutionActionError] = useState<string | null>(null);

  // Filter resolution evidence and determine active resolution attempt
  const resolutionEvidences = useMemo(() => {
    return caseEvidence.filter(
      (ev) => ev.evidence_type === CivicEvidenceType.RESOLUTION_EVIDENCE || (ev.evidence_type as string) === 'RESOLUTION_EVIDENCE'
    );
  }, [caseEvidence]);

  const activeResolutionEvidence = useMemo(() => {
    if (resolutionEvidences.length === 0) return null;
    const activeAttempt = caseRecord?.active_resolution_attempt;
    if (activeAttempt) {
      return (
        resolutionEvidences.find(
          (ev) => ev.resolution_attempt === activeAttempt || ev.evidence_id === activeAttempt
        ) || resolutionEvidences[resolutionEvidences.length - 1]
      );
    }
    return resolutionEvidences[resolutionEvidences.length - 1];
  }, [resolutionEvidences, caseRecord?.active_resolution_attempt]);

  const isCaseOwner = Boolean(
    caseRecord &&
    effectiveRole === ApplicationRole.CITIZEN &&
    effectivePid &&
    caseRecord.owner_id === effectivePid
  );

  // Auto-track initialCaseId if provided
  useEffect(() => {
    if (initialCaseId && initialCaseId.trim().length > 0) {
      setCaseIdInput(initialCaseId);
      handleTrack(initialCaseId.trim());
    }
  }, [initialCaseId]);

  // Accessibility: Close transition confirmation modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (confirmModalOpen) setConfirmModalOpen(false);
        if (acceptModalOpen) setAcceptModalOpen(false);
        if (rejectModalOpen) setRejectModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmModalOpen, acceptModalOpen, rejectModalOpen]);

  // Main Tracking Handler
  const handleTrack = async (targetId: string) => {
    const id = targetId.trim();
    if (!id) {
      setError('Please enter a valid Case ID.');
      return;
    }

    setLoading(true);
    setError(null);
    setWorkflowError(null);
    setWorkflowSuccessMsg(null);

    try {
      // 1. Always load public tracking projection
      const data = await trackingApi.getTracking(id);
      setProjection(data);

      // 2. Refresh detailed record & history in background
      await loadSupplementalData(id, data.status);
    } catch (err: any) {
      setProjection(null);
      setCaseRecord(null);
      setError(err.message || 'Unable to retrieve case tracking record. Please verify the Case ID.');
    } finally {
      setLoading(false);
    }
  };

  // Load supplemental case details & audit events based on current workspace actor
  const loadSupplementalData = async (caseId: string, _currentStatus?: string) => {
    // Try loading case details (succeeds if authorized)
    try {
      const fullCase = await casesApi.getCase(
        caseId,
        effectiveRole,
        effectivePid,
        effectiveDept as any
      );
      setCaseRecord(fullCase);
    } catch {
      setCaseRecord(null);
    }

    // Try loading case evidence
    try {
      const evList = await evidenceApi.listEvidence(caseId);
      setCaseEvidence(evList);
    } catch {
      setCaseEvidence([]);
    }

    // Try loading sanitized history
    try {
      const hist = await casesApi.getHistory(
        caseId,
        effectiveRole,
        effectivePid,
        effectiveDept as any
      );
      setCaseHistory(hist);
    } catch {
      setCaseHistory([]);
    }

    // If currently on AUDIT mode, refresh audit trail
    if (activeMode === 'AUDIT') {
      await fetchAuditTrail(caseId);
    }
  };

  // Citizen Accept Resolution Handler (Direct Closure Gate)
  // SECURITY: Identity is resolved exclusively from the server-side session cookie.
  // No role/principal simulation headers are forwarded.
  const handleAcceptResolution = async () => {
    if (!projection) return;
    setResolutionActionLoading(true);
    setResolutionActionError(null);
    try {
      const updated = await casesApi.acceptResolution(
        projection.case_id,
        { feedback: citizenFeedback.trim() || undefined }
      );
      setCaseRecord(updated);
      setProjection((prev) => (prev ? { ...prev, status: updated.status } : null));
      setWorkflowSuccessMsg('Resolution confirmed! Civic docket is now RESOLVED and closed.');
      setAcceptModalOpen(false);
      setCitizenFeedback('');
      await loadSupplementalData(projection.case_id);
    } catch (err: any) {
      setResolutionActionError(err.message || 'Failed to accept resolution.');
    } finally {
      setResolutionActionLoading(false);
    }
  };

  // Citizen Reject Resolution Handler
  // SECURITY: Identity is resolved exclusively from the server-side session cookie.
  // No role/principal simulation headers are forwarded.
  const handleRejectResolution = async () => {
    if (!projection) return;
    if (rejectionReason.trim().length < 5) {
      setResolutionActionError('Please provide a substantive reason (at least 5 characters) explaining what remains unresolved.');
      return;
    }
    setResolutionActionLoading(true);
    setResolutionActionError(null);
    try {
      const updated = await casesApi.rejectResolution(
        projection.case_id,
        { reason: rejectionReason.trim() }
      );
      setCaseRecord(updated);
      setProjection((prev) => (prev ? { ...prev, status: updated.status } : null));
      setWorkflowSuccessMsg('Resolution rejected. The case remains in UNDER_REVIEW for municipal rework.');
      setRejectModalOpen(false);
      setRejectionReason('');
      await loadSupplementalData(projection.case_id);
    } catch (err: any) {
      setResolutionActionError(err.message || 'Failed to reject resolution.');
    } finally {
      setResolutionActionLoading(false);
    }
  };

  // Fetch Audit Trail with Cedar fail-closed evaluation
  const fetchAuditTrail = async (caseId: string) => {
    setAuditLoading(true);
    setAuditRestricted(false);
    try {
      const events = await auditApi.getCaseAuditTrail(
        caseId,
        effectiveRole,
        effectivePid,
        effectiveDept as any
      );
      setAuditEvents(events);
      setAuditRestricted(false);
    } catch {
      // Server returned 403 Forbidden due to Cedar PEP
      setAuditEvents([]);
      setAuditRestricted(true);
    } finally {
      setAuditLoading(false);
    }
  };

  // Re-fetch audit when mode switches to AUDIT or workspace actor changes
  useEffect(() => {
    if (projection && activeMode === 'AUDIT') {
      fetchAuditTrail(projection.case_id);
    }
  }, [activeMode, effectiveRole, effectiveDept, effectivePid]);

  const handleCopyId = () => {
    if (projection?.case_id) {
      navigator.clipboard.writeText(projection.case_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Helper to get step index
  const getStatusStepIndex = (statusStr: string) => {
    const s = statusStr.toUpperCase().replace(/\s+/g, '_');
    if (s === 'DRAFT' || s === 'DOCKET_CREATED') return 1;
    if (s === 'TRIAGED' || s === 'ROUTING_PREPARED') return 2;
    if (s === 'SUBMISSION_READY') return 3;
    if (s === 'ASSIGNED' || s === 'IN_PROGRESS' || s === 'UNDER_REVIEW') return 4;
    if (s === 'RESOLVED') return 5;
    return 1;
  };

  const currentStatusEnum = (projection?.status as CaseStatus) || CaseStatus.DOCKET_CREATED;
  const currentStep = projection ? getStatusStepIndex(projection.status) : 0;
  const nextTransition = VALID_NEXT_TRANSITIONS[currentStatusEnum];

  // Perform Canonical Single-Step Status Transition
  const handleExecuteTransition = async () => {
    if (!projection || !nextTransition) return;

    setWorkflowActionLoading(true);
    setWorkflowError(null);

    try {
      // Execute stage advancement along valid next path
      const updated = await casesApi.updateStatus(
        projection.case_id,
        {
          status: nextTransition.nextStatus,
          note: transitionNote.trim() || undefined,
        },
        effectiveRole,
        effectivePid,
        effectiveDept as any
      );

      // Update state
      setCaseRecord(updated);
      setProjection((prev) => (prev ? { ...prev, status: updated.status } : null));
      setWorkflowSuccessMsg(
        `Case successfully transitioned to ${updated.status.replace(/_/g, ' ')}.`
      );
      setConfirmModalOpen(false);
      setTransitionNote('');

      // Refresh supplemental info
      await loadSupplementalData(projection.case_id, updated.status);
    } catch (err: any) {
      setWorkflowError(
        err.message || 'Status transition denied. Verify authority role and department scope.'
      );
      setConfirmModalOpen(false);
    } finally {
      setWorkflowActionLoading(false);
    }
  };

  // Add Authority Resolution Note
  const handleAddResolutionNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projection || !newResolutionNote.trim()) return;

    setResolutionSubmitting(true);
    setWorkflowError(null);
    try {
      const updated = await casesApi.addResolutionNote(
        projection.case_id,
        { note: newResolutionNote.trim() },
        effectiveRole,
        effectivePid,
        effectiveDept as any
      );
      setCaseRecord(updated);
      setNewResolutionNote('');
      setWorkflowSuccessMsg('Resolution note recorded into authority workflow.');
      await loadSupplementalData(projection.case_id);
    } catch (err: any) {
      setWorkflowError(
        err.message || 'Failed to add resolution note. Authority authorization required.'
      );
    } finally {
      setResolutionSubmitting(false);
    }
  };

  // Case map markers: ONLY use genuine case latitude/longitude if available on the case record
  const caseCoords = caseRecord && caseRecord.latitude != null && caseRecord.longitude != null
    ? [caseRecord.latitude, caseRecord.longitude] as [number, number]
    : null;

  const caseMarkers: MapMarkerItem[] = caseCoords && caseRecord
    ? [
        {
          id: caseRecord.case_id,
          lat: caseCoords[0],
          lng: caseCoords[1],
          category: 'ROAD',
          title: `Case ${caseRecord.case_id}`,
          subtitle: `Location: ${caseRecord.location || 'Text Reference'}`,
          department: caseRecord.department,
          urgency: caseRecord.urgency || undefined,
          status: caseRecord.status,
        },
      ]
    : [];

  // Check if simulated department matches case
  const isDeptMismatch =
    projection &&
    effectiveRole === ApplicationRole.AUTHORITY_OFFICER &&
    effectiveDept !== projection.recommended_department;

  return (
    <div className="civic-tracking-view crosshair-corner" aria-label="Civic Action Journey">
      {/* Header Bar */}
      <div className="tracking-header-block">
        <div className="tracking-prehead">
          <span className="technical-label">CIVIC CASE WORKSPACE // TRACK DOCKET</span>
        </div>
        <h2 className="tracking-view-title">Track Civic Action Docket</h2>
        <p className="tracking-view-sub">
          Verify public tracking progression, inspect lifecycle milestones, and execute authorized status transitions.
        </p>
      </div>

      {/* COMPACT WORKSPACE IDENTITY STRIP (No simulated controls, strictly server-authoritative) */}
      <div className="workspace-identity-strip" role="status" aria-label="Workspace Identity">
        <div className="workspace-identity-meta">
          <span className="workspace-identity-dot" />
          <span className="technical-label">PROTOTYPE WORKSPACE IDENTITY // SERVER AUTH:</span>
          <strong className="identity-role-label">{effectiveName}</strong>
          <span className="identity-role-badge">[{effectiveRole.replace(/_/g, ' ')}]</span>
          {effectiveDept && (
            <span className="identity-dept-label">[{String(effectiveDept).replace(/_/g, ' ')}]</span>
          )}
          <span className="identity-pid-label">({effectivePid})</span>
        </div>
        <div className="identity-security-pill">
          <Lock size={12} color="var(--civic-emerald)" />
          <span>CEDAR PEP ACTIVE</span>
        </div>
      </div>

      {/* ROLE-AWARE WORKSPACE MODES (Exposed only for authorized authority/admin roles) */}
      {(effectiveRole === ApplicationRole.AUTHORITY_OFFICER ||
        effectiveRole === ApplicationRole.MUNICIPAL_SUPERVISOR ||
        effectiveRole === ApplicationRole.ADMINISTRATOR) && (
        <div className="tracking-mode-switcher" role="tablist" aria-label="Workspace Modes">
          <button
            type="button"
            role="tab"
            aria-selected={activeMode === 'PUBLIC'}
            className={`tracking-mode-btn ${activeMode === 'PUBLIC' ? 'active' : ''}`}
            onClick={() => setActiveMode('PUBLIC')}
          >
            <Lock size={13} />
            <span>1. PUBLIC-SAFE TRACKING</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeMode === 'AUTHORITY'}
            className={`tracking-mode-btn mode-authority ${activeMode === 'AUTHORITY' ? 'active' : ''}`}
            onClick={() => setActiveMode('AUTHORITY')}
          >
            <Building2 size={13} />
            <span>2. AUTHORITY WORKFLOW</span>
          </button>

          {(effectiveRole === ApplicationRole.MUNICIPAL_SUPERVISOR ||
            effectiveRole === ApplicationRole.ADMINISTRATOR) && (
            <button
              type="button"
              role="tab"
              aria-selected={activeMode === 'AUDIT'}
              className={`tracking-mode-btn mode-audit ${activeMode === 'AUDIT' ? 'active' : ''}`}
              onClick={() => setActiveMode('AUDIT')}
            >
              <ShieldCheck size={13} />
              <span>3. AUTHORIZED AUDIT TRAIL</span>
            </button>
          )}
        </div>
      )}

      {/* Query Bar */}
      <form
        className="tracking-query-bar"
        onSubmit={(e) => {
          e.preventDefault();
          handleTrack(caseIdInput);
        }}
      >
        <div className="query-input-shell">
          <Search size={15} className="query-icon" />
          <input
            type="text"
            className="query-input-field"
            placeholder="Enter Case ID (e.g. NS-CHN-2026-821F or civic-case-...)"
            value={caseIdInput}
            onChange={(e) => setCaseIdInput(e.target.value)}
            aria-label="Civic Case ID"
          />
        </div>
        <button
          type="submit"
          className="btn-query-submit"
          disabled={loading || !caseIdInput.trim()}
        >
          {loading ? 'LOOKING UP...' : 'TRACK DOCKET'}
        </button>
      </form>

      {/* Recent Dockets Row */}
      <div className="recent-dockets-section">
        <div className="recent-section-header">
          <span className="technical-label">RECENT CIVIC ACTION DOCKETS</span>
          <span className="recent-disclaimer-note">Locally generated records • Not official government cases</span>
        </div>

        <div className="recent-dockets-cards-grid">
          {[
            ...(recentCaseIds.length > 0
              ? recentCaseIds.map((id) => ({
                  caseId: id,
                  issue: 'Civic Grievance',
                  department: 'Recommended Department',
                  status: 'DOCKET CREATED',
                }))
              : [
                  {
                    caseId: 'NS-CHN-2026-14CE',
                    issue: 'Waterlogging Defect',
                    department: 'Drainage / Stormwater',
                    status: 'DOCKET CREATED',
                  },
                  {
                    caseId: 'NS-CHN-2026-821F',
                    issue: 'Road Crater Hazard',
                    department: 'PWD / Roads',
                    status: 'ROUTING PREPARED',
                  },
                  {
                    caseId: 'NS-CHN-2026-4B90',
                    issue: 'Streetlight Outage',
                    department: 'Electrical / Streetlights',
                    status: 'SUBMISSION READY',
                  },
                ]),
          ].slice(0, 3).map((item) => (
            <button
              key={item.caseId}
              type="button"
              className={`recent-docket-card ${caseIdInput === item.caseId ? 'selected' : ''}`}
              onClick={() => {
                setCaseIdInput(item.caseId);
                handleTrack(item.caseId);
              }}
              aria-label={`Track recent docket ${item.caseId}`}
            >
              <div className="docket-card-top">
                <span className="docket-id-text">{item.caseId}</span>
                <span className="docket-status-badge">{item.status}</span>
              </div>
              <div className="docket-card-issue">{item.issue}</div>
              <div className="docket-card-dept">{item.department}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="tracking-alert-card" role="alert">
          <AlertCircle size={16} />
          <div>
            <div className="alert-title">Case Lookup Failed</div>
            <div className="alert-body">{error}</div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!projection && !loading && (
        <div className="tracking-empty-workspace crosshair-corner animate-fade-in" role="region" aria-label="Tracking Workspace Intro">
          <div className="empty-workspace-top">
            <span className="technical-label">PUBLIC CIVIC ACTION LIFECYCLE AUDIT</span>
            <span className="empty-status-tag">STANDBY // ENTER DOCKET ID</span>
          </div>

          <h3 className="empty-title">Follow the complete lifecycle of your civic docket.</h3>
          <p className="empty-desc">
            Search with any valid Case ID or choose one of the sample dockets above to inspect the recommended department routing, public-safe progression, and Cedar-protected audit trail.
          </p>

          <div className="journey-preview-timeline">
            <div className="preview-step">
              <span className="p-num">01</span>
              <div>
                <strong>Docket Created</strong>
                <p>Grievance structured into record</p>
              </div>
            </div>
            <div className="preview-connector">→</div>
            <div className="preview-step">
              <span className="p-num">02</span>
              <div>
                <strong>Routing Prepared</strong>
                <p>Recommended department jurisdiction</p>
              </div>
            </div>
            <div className="preview-connector">→</div>
            <div className="preview-step">
              <span className="p-num">03</span>
              <div>
                <strong>Submission Ready</strong>
                <p>Prepared for authority intake</p>
              </div>
            </div>
            <div className="preview-connector">→</div>
            <div className="preview-step">
              <span className="p-num">04</span>
              <div>
                <strong>Under Review</strong>
                <p>Authority review stage</p>
              </div>
            </div>
            <div className="preview-connector">→</div>
            <div className="preview-step">
              <span className="p-num">05</span>
              <div>
                <strong>Resolved</strong>
                <p>Resolution recorded in workflow</p>
              </div>
            </div>
          </div>

          <div className="empty-footer-disclaimer">
            PROTOTYPE • NOT A GOVERNMENT PORTAL • This record is generated by JARVIS Civic and is not proof of official government submission or resolution.
          </div>
        </div>
      )}

      {/* ACTIVE CASE SELECTED */}
      {projection && (
        <div className="case-intelligence-workspace animate-fade-in">
          {/* Top Case Identity & Status Strip */}
          <div className="workspace-top-bar crosshair-corner">
            <div className="top-bar-identity">
              <span className="technical-label">CIVIC CASE IDENTIFIER</span>
              <div className="top-case-id-row">
                <span className="top-case-id-text">{projection.case_id}</span>
                <button
                  type="button"
                  className="btn-copy-tag"
                  onClick={handleCopyId}
                  title="Copy Case ID"
                  aria-label="Copy Case ID"
                >
                  {copied ? <Check size={12} color="var(--civic-emerald)" /> : <Copy size={12} />}
                  <span>{copied ? 'COPIED' : 'COPY'}</span>
                </button>
              </div>
            </div>

            <div className="top-bar-status-pill" data-status={projection.status}>
              <span className="status-bullet">●</span>
              <span className="status-text">{projection.status.replace(/_/g, ' ')}</span>
            </div>
          </div>

          {/* Workflow Feedback Messages */}
          {workflowSuccessMsg && (
            <div className="public-safe-banner animate-fade-in" style={{ borderColor: 'var(--civic-emerald)' }}>
              <div className="public-safe-tag">
                <Check size={14} color="var(--civic-emerald)" />
                <span className="technical-label" style={{ color: 'var(--civic-emerald)' }}>WORKFLOW UPDATED</span>
              </div>
              <span className="public-safe-detail">{workflowSuccessMsg}</span>
            </div>
          )}

          {workflowError && (
            <div className="tracking-alert-card animate-fade-in" role="alert">
              <AlertCircle size={16} />
              <div>
                <div className="alert-title">Operation Denied</div>
                <div className="alert-body">{workflowError}</div>
              </div>
            </div>
          )}

          {/* =========================================================================
              MODE 1: PUBLIC-SAFE TRACKING VIEW (DEFAULT)
              ========================================================================= */}
          {activeMode === 'PUBLIC' && (
            <>
              {/* Public Safety Guarantee Strip */}
              <div className="public-safe-banner" role="note">
                <div className="public-safe-tag">
                  <Lock size={12} color="var(--civic-emerald)" />
                  <span className="technical-label" style={{ color: 'var(--civic-emerald)' }}>PUBLIC-SAFE TRACKING</span>
                </div>
                <span className="public-safe-detail">
                  Only non-sensitive metadata (Case ID, Status, Department, Timestamps) is publicly queryable.
                  Citizen identity, contact numbers, and private audit trails are strictly shielded by Cedar PEP.
                </span>
              </div>

              {/* Quick Stats Grid */}
              <div className="case-stats-row">
                <div className="case-stat-cell">
                  <span className="stat-label">ISSUE INTENT</span>
                  <span className="stat-val">Civic Grievance Record</span>
                </div>
                <div className="case-stat-cell">
                  <span className="stat-label">LOCATION REFERENCE</span>
                  <span className="stat-val">
                    <MapPin size={12} color="var(--civic-cyan)" />
                    <span>Textual Reference (Privacy Shielded)</span>
                  </span>
                </div>
                <div className="case-stat-cell">
                  <span className="stat-label">RECOMMENDED DEPARTMENT</span>
                  <span className="stat-val highlight-dept">
                    <Building2 size={12} />
                    <span>{projection.recommended_department.replace(/_/g, ' ')}</span>
                  </span>
                </div>
                <div className="case-stat-cell">
                  <span className="stat-label">ASSESSED URGENCY</span>
                  <span className="stat-val urgency-val">MEDIUM // RECORDED</span>
                </div>
                <div className="case-stat-cell">
                  <span className="stat-label">CREATED TIMESTAMP</span>
                  <span className="stat-val">{new Date(projection.created_at).toLocaleString()}</span>
                </div>
              </div>

              {/* Phase 8.8: Citizen Resolution Review & Closure Gate Card */}
              {(activeResolutionEvidence || caseRecord?.resolution_confirmed || (caseRecord?.rejection_count && caseRecord.rejection_count > 0)) && (
                <div
                  className={`citizen-resolution-review-card ${
                    projection.status === CaseStatus.RESOLVED && caseRecord?.resolution_confirmed
                      ? 'confirmed'
                      : projection.status === CaseStatus.UNDER_REVIEW && caseRecord?.rejection_count && caseRecord.rejection_count > 0 && !activeResolutionEvidence
                      ? 'rejected'
                      : 'pending'
                  } animate-fade-in`}
                >
                  <div className="res-review-header">
                    <div>
                      <span className="technical-label">
                        {projection.status === CaseStatus.RESOLVED && caseRecord?.resolution_confirmed
                          ? 'CITIZEN RESOLUTION CONFIRMED // FINAL CLOSURE'
                          : projection.status === CaseStatus.UNDER_REVIEW && caseRecord?.rejection_count && caseRecord.rejection_count > 0 && !activeResolutionEvidence
                          ? 'RESOLUTION REWORK REQUIRED // CITIZEN FEEDBACK'
                          : 'CITIZEN RESOLUTION REVIEW REQUIRED'}
                      </span>
                      <h4 className="res-review-title">
                        {projection.status === CaseStatus.RESOLVED && caseRecord?.resolution_confirmed
                          ? 'Resolution Confirmed by Citizen'
                          : projection.status === CaseStatus.UNDER_REVIEW && caseRecord?.rejection_count && caseRecord.rejection_count > 0 && !activeResolutionEvidence
                          ? 'Resolution Rejected by Citizen — Rework Required'
                          : 'Resolution Evidence Submitted — Citizen Review Required'}
                      </h4>
                      <p className="res-review-desc">
                        {projection.status === CaseStatus.RESOLVED && caseRecord?.resolution_confirmed
                          ? 'The citizen case owner has verified evidence and accepted resolution. The docket is officially RESOLVED and closed.'
                          : projection.status === CaseStatus.UNDER_REVIEW && caseRecord?.rejection_count && caseRecord.rejection_count > 0 && !activeResolutionEvidence
                          ? `The citizen rejected the previous resolution attempt. Corrective action is required by ${projection.recommended_department.replace(/_/g, ' ')}.`
                          : 'Department authority has submitted resolution evidence. Review the evidence, deterministic validation, and AI advisory assessment below to confirm closure or request rework.'}
                      </p>
                    </div>
                    <span className="privacy-shield-pill">
                      {projection.status === CaseStatus.RESOLVED ? 'CASE RESOLVED' : 'CLOSURE GATE'}
                    </span>
                  </div>

                  {/* Resolution Evidence Details */}
                  {activeResolutionEvidence && (
                    <div className="res-evidence-list">
                      <div className="res-evidence-item">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Paperclip size={14} color="var(--civic-cyan)" />
                          <span style={{ fontWeight: 600 }}>{activeResolutionEvidence.filename}</span>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                            ({(activeResolutionEvidence.size_bytes / 1024).toFixed(1)} KB)
                          </span>
                        </div>
                        <div className="res-evidence-meta">
                          <span
                            className={`res-pill ${
                              activeResolutionEvidence.validation_status === 'VALID' ? 'valid' : 'ai-rejected'
                            }`}
                          >
                            Evidence validation: {activeResolutionEvidence.validation_status}
                          </span>
                          <span
                            className={`res-pill ${
                              activeResolutionEvidence.verification_status === 'VERIFIED'
                                ? 'ai-verified'
                                : activeResolutionEvidence.verification_status === 'UNCERTAIN'
                                ? 'ai-uncertain'
                                : 'ai-rejected'
                            }`}
                          >
                            AI-assisted assessment: {activeResolutionEvidence.verification_status}
                            {activeResolutionEvidence.ai_confidence != null && (
                              ` (${Math.round(activeResolutionEvidence.ai_confidence * 100)}%)`
                            )}
                          </span>
                        </div>
                      </div>

                      {/* Advisory Disclaimer */}
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', fontStyle: 'italic', paddingLeft: '0.2rem' }}>
                        Advisory Disclaimer: Evidence validation reflects deterministic integrity (format, size, hash). AI-assisted assessment is non-binding and advisory. Only the citizen case owner has the final closure authority.
                      </div>
                    </div>
                  )}

                  {/* Citizen Rejection Note if exists */}
                  {caseRecord?.citizen_feedback && (
                    <div className="rejection-reason-quote">
                      <strong>Citizen Feedback / Rework Request:</strong> "{caseRecord.citizen_feedback}"
                      {caseRecord.rejection_count != null && caseRecord.rejection_count > 0 && (
                        <span style={{ marginLeft: '0.5rem', color: 'var(--civic-amber)', fontSize: '0.72rem' }}>
                          (Rejection Count: {caseRecord.rejection_count})
                        </span>
                      )}
                    </div>
                  )}

                  {/* Authority Resolution Notes / Claim */}
                  {caseRecord?.resolution_notes && caseRecord.resolution_notes.length > 0 && (
                    <div className="rejection-reason-quote" style={{ borderLeftColor: 'var(--civic-cyan)' }}>
                      <strong>Authority Resolution Claim:</strong> "{caseRecord.resolution_notes[caseRecord.resolution_notes.length - 1]}"
                    </div>
                  )}

                  {/* Citizen Action Buttons (Under Review + Owner + Deterministic Valid Evidence) */}
                  {projection.status === CaseStatus.UNDER_REVIEW && activeResolutionEvidence && (
                    <div className="res-actions-row">
                      {isCaseOwner ? (
                        <>
                          <button
                            type="button"
                            className="btn-accept-resolution"
                            onClick={() => setAcceptModalOpen(true)}
                            disabled={activeResolutionEvidence.validation_status !== 'VALID' || resolutionActionLoading}
                          >
                            <CheckCircle2 size={15} />
                            <span>ACCEPT RESOLUTION</span>
                          </button>
                          <button
                            type="button"
                            className="btn-reject-resolution"
                            onClick={() => setRejectModalOpen(true)}
                            disabled={resolutionActionLoading}
                          >
                            <XCircle size={15} />
                            <span>REJECT / REQUEST REWORK</span>
                          </button>
                        </>
                      ) : (
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          {effectiveRole === ApplicationRole.CITIZEN
                            ? 'You are signed in as a citizen, but only the specific case owner can accept or reject this resolution.'
                            : 'Awaiting citizen case-owner resolution review. Authority and administrative accounts cannot confirm resolution on behalf of the citizen.'}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Confirmed State Summary */}
                  {projection.status === CaseStatus.RESOLVED && caseRecord?.resolution_confirmed && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--civic-emerald)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.2rem' }}>
                      <CheckCircle2 size={15} />
                      <span>Citizen resolution confirmation: ACCEPTED ({caseRecord.resolution_confirmed_at ? new Date(caseRecord.resolution_confirmed_at).toLocaleString() : 'Confirmed'})</span>
                    </div>
                  )}
                </div>
              )}

              {/* Split Layout: Left Lifecycle Journey, Right Case Map */}
              <div className="workspace-split-body">
                {/* Left: Connected 5-Stage Case Journey */}
                <div className="workspace-journey-col crosshair-corner">
                  <div className="journey-col-header">
                    <span className="technical-label">CIVIC CASE JOURNEY // 5 STAGES</span>
                    <span className="active-stage-indicator">STAGE 0{currentStep} OF 05</span>
                  </div>

                  <div className="connected-journey-timeline">
                    {CANONICAL_JOURNEY.map((stepItem) => {
                      const isPassed = currentStep > stepItem.step;
                      const isCurrent = currentStep === stepItem.step;

                      return (
                        <div
                          key={stepItem.step}
                          className={`timeline-journey-node ${isPassed ? 'node-passed' : ''} ${
                            isCurrent ? 'node-current' : ''
                          }`}
                        >
                          <div className="node-marker-wrap">
                            <div className="node-beacon-ring">
                              <span className="node-bullet-core">
                                {isPassed ? '✓' : stepItem.step}
                              </span>
                            </div>
                            {stepItem.step < CANONICAL_JOURNEY.length && (
                              <div className={`node-stem-connector ${isPassed ? 'connector-passed' : ''}`} />
                            )}
                          </div>

                          <div className="node-details-wrap">
                            <div className="node-header-line">
                              <span className="node-title-text">{stepItem.label}</span>
                              {isCurrent && <span className="node-live-tag">CURRENT STATUS</span>}
                            </div>
                            <p className="node-desc-text">{stepItem.desc}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Attach Evidence Link */}
                  {onSelectCaseForEvidence && (
                    <div className="journey-evidence-banner">
                      <div className="evidence-banner-info">
                        <Paperclip size={15} color="var(--civic-cyan)" />
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '0.84rem' }}>Have photographic proof?</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            Add photos or audio evidence to strengthen this civic record.
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn-attach-evidence-link"
                        onClick={() => onSelectCaseForEvidence(projection.case_id)}
                      >
                        <span>OPEN EVIDENCE STUDIO</span>
                        <ArrowRight size={13} />
                      </button>
                    </div>
                  )}
                </div>

                {/* Right: Integrated Case Map / Spatial Telemetry */}
                <div className="workspace-map-col crosshair-corner">
                  <div className="map-col-header">
                    <div className="map-header-left">
                      <Globe size={14} color="var(--civic-cyan)" />
                      <span className="technical-label">GEOSPATIAL AUDIT REFERENCE</span>
                    </div>
                    <span className="privacy-shield-pill">PRIVACY SHIELDED</span>
                  </div>

                  <div className="case-map-frame">
                    <CivicMap
                      center={caseCoords || [13.0604, 80.2496]}
                      zoom={caseCoords ? 14 : 11}
                      markers={caseMarkers}
                      mode="case_tracking"
                      interactive={false}
                      allowManualPin={false}
                      locationName={caseRecord?.location || 'Location provided as text reference'}
                      className="tracking-case-leaflet-map"
                    />
                  </div>

                  <div className="case-spatial-note">
                    <span className="note-icon">ℹ</span>
                    <span>
                      {caseCoords
                        ? 'Citizen-selected map coordinates confirmed on docket.'
                        : 'Exact map position unavailable. Location provided as text reference; physical coordinates withheld on unauthenticated queries.'}
                    </span>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* =========================================================================
              MODE 2: AUTHORITY WORKFLOW UI
              ========================================================================= */}
          {activeMode === 'AUTHORITY' && (
            <div className="authority-workspace-card crosshair-corner animate-fade-in">
              <div className="workspace-top-bar" style={{ padding: 0, border: 'none' }}>
                <div>
                  <span className="technical-label">AUTHORITY WORKFLOW CONSOLE</span>
                  <h3 style={{ margin: '0.2rem 0', fontSize: '1.25rem', color: 'var(--text-primary)' }}>
                    Departmental Review & Status Transitions
                  </h3>
                </div>
                <span className="simulation-badge">CEDAR AUTHORIZED WORKFLOW</span>
              </div>

              {/* Department Mismatch Alert */}
              {isDeptMismatch && (
                <div className="dept-mismatch-banner">
                  <AlertTriangle size={18} color="#f87171" style={{ flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div className="dept-mismatch-title">DEPARTMENT SCOPE MISMATCH DETECTED</div>
                    <div className="dept-mismatch-desc">
                      Case is assigned to <strong>{projection.recommended_department}</strong>, but current actor workspace is configured as <strong>{session.department}</strong>.
                      Cedar Policy will reject workflow mutations under fail-closed departmental scoping. Switch to an authority workspace with matching department jurisdiction.
                    </div>
                  </div>
                </div>
              )}

              {/* Stage Transition Panel */}
              <div className="authority-stage-transition-panel">
                <div className="transition-header-row">
                  <div>
                    <span className="technical-label">CANONICAL LIFECYCLE PROGRESSION</span>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                      Strict single-step forward progression. Skipping stages and backward shifts are rejected.
                    </div>
                  </div>
                  <span className="docket-status-badge">CURRENT: {projection.status.replace(/_/g, ' ')}</span>
                </div>

                <div className="transition-flow-visual">
                  <div className="stage-badge-node">
                    <span className="s-label">CURRENT STAGE</span>
                    <span className="s-val">{projection.status.replace(/_/g, ' ')}</span>
                  </div>

                  <span className="transition-arrow-symbol">→</span>

                  <div className="stage-badge-node next">
                    <span className="s-label">ALLOWED NEXT STAGE</span>
                    <span className="s-val">
                      {nextTransition
                        ? nextTransition.nextStatus.replace(/_/g, ' ')
                        : projection.status === CaseStatus.UNDER_REVIEW
                        ? 'CITIZEN CONFIRMATION REQUIRED'
                        : 'LIFECYCLE COMPLETED'}
                    </span>
                  </div>
                </div>

                {nextTransition ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', maxWidth: '460px' }}>
                      {nextTransition.actionDesc}
                    </div>
                    <button
                      type="button"
                      className="btn-advance-status"
                      onClick={() => setConfirmModalOpen(true)}
                      disabled={workflowActionLoading}
                    >
                      <FileCheck2 size={15} />
                      <span>{nextTransition.label}</span>
                      <ArrowRight size={14} />
                    </button>
                  </div>
                ) : projection.status === CaseStatus.UNDER_REVIEW ? (
                  <div className="authority-resolution-status-box">
                    <div className={`gate-status-tag ${
                      caseRecord?.rejection_count && caseRecord.rejection_count > 0 && !activeResolutionEvidence
                        ? 'rejected'
                        : activeResolutionEvidence
                        ? 'pending'
                        : 'no-evidence'
                    }`}>
                      {caseRecord?.rejection_count && caseRecord.rejection_count > 0 && !activeResolutionEvidence ? (
                        <>
                          <AlertTriangle size={16} color="var(--civic-amber)" />
                          <span>Citizen Rejected Resolution — Corrective Action Required</span>
                        </>
                      ) : (
                        <>
                          <Clock size={16} color="var(--civic-cyan)" />
                          <span>Awaiting Citizen Confirmation</span>
                        </>
                      )}
                    </div>
                    <p className="gate-note">
                      {caseRecord?.rejection_count && caseRecord.rejection_count > 0 && !activeResolutionEvidence
                        ? `The citizen rejected the previous resolution attempt ("${caseRecord.citizen_feedback || 'Rework requested'}"). Case closure is strictly gated on citizen acceptance. Corrective action and new resolution evidence must be submitted.`
                        : 'Resolution closure is strictly citizen-gated. Authority officers cannot bypass citizen confirmation or force status to RESOLVED.'}
                    </p>
                  </div>
                ) : (
                  <div className="authority-resolution-status-box">
                    <div className="gate-status-tag confirmed">
                      <CheckCircle2 size={16} color="var(--civic-emerald)" />
                      <span>Citizen Confirmed Resolution — Case Closed</span>
                    </div>
                    <p className="gate-note">
                      ✓ The case owner citizen confirmed resolution on {caseRecord?.resolution_confirmed_at ? new Date(caseRecord.resolution_confirmed_at).toLocaleString() : 'docket'}. The case is officially RESOLVED and closed.
                    </p>
                  </div>
                )}
              </div>

              {/* Resolution Record Panel */}
              <div className="resolution-section-panel">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <span className="technical-label">AUTHORITY RESOLUTION RECORD</span>
                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                      System-recorded civic resolution log. Notes are attributable and append-only.
                    </div>
                  </div>
                  <span className="privacy-shield-pill">ATTRIBUTED</span>
                </div>

                {/* Existing Resolution Notes */}
                {caseRecord?.resolution_notes && caseRecord.resolution_notes.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {caseRecord.resolution_notes.map((note, idx) => (
                      <div key={idx} className="resolution-record-item">
                        <div className="resolution-meta-row">
                          <span>RECORD #{idx + 1} // AUTHORITY LOG</span>
                          <span>{new Date().toLocaleDateString()}</span>
                        </div>
                        <div className="resolution-text">{note}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>
                    No resolution notes recorded for this case yet.
                  </div>
                )}

                {/* Add Note Form */}
                <form onSubmit={handleAddResolutionNote} style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                  <input
                    type="text"
                    className="sim-field-input"
                    style={{ flex: 1 }}
                    placeholder="Enter departmental resolution observation or field note..."
                    value={newResolutionNote}
                    onChange={(e) => setNewResolutionNote(e.target.value)}
                    disabled={resolutionSubmitting}
                  />
                  <button
                    type="submit"
                    className="btn-query-submit"
                    disabled={resolutionSubmitting || !newResolutionNote.trim()}
                  >
                    <Send size={13} />
                    <span>{resolutionSubmitting ? 'SAVING...' : 'ADD NOTE'}</span>
                  </button>
                </form>
              </div>

              {/* Case History Milestones */}
              {caseHistory.length > 0 && (
                <div style={{ marginTop: '0.5rem' }}>
                  <span className="technical-label">SANITIZED CASE HISTORY MILESTONES</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                    {caseHistory.map((item) => (
                      <div key={item.milestone_id} className="resolution-record-item" style={{ borderLeftColor: 'var(--civic-cyan)' }}>
                        <div className="resolution-meta-row">
                          <span style={{ color: 'var(--civic-cyan)' }}>{item.stage || item.status.replace(/_/g, ' ')}</span>
                          <span>{new Date(item.timestamp).toLocaleString()}</span>
                        </div>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{item.label}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.description}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              MODE 3: AUTHORIZED AUDIT TRAIL UI
              ========================================================================= */}
          {activeMode === 'AUDIT' && (
            <div className="animate-fade-in">
              {/* Security Banner */}
              <div className="audit-security-banner">
                <div className="audit-banner-tag">
                  <ShieldCheck size={16} />
                  <span>CEDAR-PROTECTED AUTHORIZED AUDIT TRAIL</span>
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--text-dim)' }}>
                  Action: read_audit_log // Fail-Closed PEP
                </span>
              </div>

              {auditLoading ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  EVALUATING CEDAR POLICIES & RETRIEVING AUDIT TRAIL...
                </div>
              ) : auditRestricted ? (
                /* RESTRICTED STATE: Zero leak */
                <div className="audit-restricted-state" role="alert">
                  <div className="restricted-lock-icon">
                    <Lock size={20} />
                  </div>
                  <div className="restricted-title">AUDIT TRAIL RESTRICTED</div>
                  <div className="restricted-sub">AUTHORITY-LEVEL AUTHORIZATION REQUIRED</div>
                  <p className="restricted-desc">
                    Access to internal system audit trails is strictly governed by Cedar authorization.
                    The current workspace principal (<strong>{session.role}</strong>) lacks permission to execute <code>read_audit_log</code> on this case.
                    Audit records are restricted to <strong>MUNICIPAL_SUPERVISOR</strong> (for assigned department) or <strong>ADMINISTRATOR</strong>.
                  </p>
                </div>
              ) : auditEvents.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                  No audit events recorded for this case yet.
                </div>
              ) : (
                /* AUTHORIZED CONNECTED TIMELINE */
                <div className="audit-timeline-container">
                  {auditEvents.map((event) => {
                    const isTransition = event.event_type === 'STATUS_TRANSITION';
                    const isNote = event.event_type === 'RESOLUTION_NOTE_ADDED';

                    return (
                      <div key={event.event_id} className="audit-event-card">
                        <div
                          className={`audit-node-dot ${
                            isTransition ? 'status-transition' : isNote ? 'resolution-note' : ''
                          }`}
                        >
                          ●
                        </div>

                        <div className="audit-content-card">
                          <div className="audit-card-top">
                            <span className="audit-event-type-badge">{event.event_type}</span>
                            <span className="audit-timestamp-text">
                              {new Date(event.timestamp).toLocaleString()}
                            </span>
                          </div>

                          <div className="audit-actor-row">
                            <span>PRINCIPAL:</span>
                            <span className="audit-actor-role-badge">
                              {event.principal_role} ({event.principal_id})
                            </span>
                            {event.principal_department && (
                              <span style={{ color: 'var(--civic-cyan)' }}>
                                [{event.principal_department}]
                              </span>
                            )}
                            <span style={{ marginLeft: 'auto', color: 'var(--civic-emerald)', fontWeight: 700 }}>
                              {event.outcome}
                            </span>
                          </div>

                          {event.previous_status && event.new_status && (
                            <div className="audit-status-shift-row">
                              <span>TRANSITION:</span>
                              <span style={{ color: 'var(--text-dim)' }}>{event.previous_status}</span>
                              <span style={{ color: 'var(--civic-cyan)' }}>→</span>
                              <span style={{ color: 'var(--civic-amber)', fontWeight: 700 }}>
                                {event.new_status}
                              </span>
                            </div>
                          )}

                          {event.metadata && event.metadata.note && (
                            <div className="audit-meta-note">
                              <strong>Note:</strong> {event.metadata.note}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Transparent Civic Notice */}
          <div className="record-disclaimer-box" role="note" style={{ marginTop: '1.5rem' }}>
            <div className="disclaimer-header-row">
              <ShieldAlert size={14} />
              <span>TRANSPARENT CIVIC NOTICE</span>
            </div>
            <p className="disclaimer-body">
              This record is generated by JARVIS Civic and is not proof of official government submission or resolution.
            </p>
          </div>
        </div>
      )}

      {/* CONFIRMATION MODAL FOR STATUS ADVANCE */}
      {confirmModalOpen && nextTransition && (
        <div className="confirm-dialog-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-transition-title">
          <div className="confirm-dialog-box crosshair-corner animate-fade-in">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Building2 size={18} color="var(--civic-amber)" />
              <h3 id="confirm-transition-title" style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-primary)' }}>
                Confirm Lifecycle Transition
              </h3>
            </div>

            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              Are you sure you want to transition case <strong>{projection?.case_id}</strong> from{' '}
              <strong style={{ color: 'var(--text-primary)' }}>{projection?.status.replace(/_/g, ' ')}</strong> to{' '}
              <strong style={{ color: 'var(--civic-amber)' }}>
                {nextTransition.nextStatus.replace(/_/g, ' ')}
              </strong>
              ? This action will be recorded in the Cedar-protected append-only audit trail.
            </div>

            <div className="sim-field-group">
              <label className="sim-field-label">Operational Note (Optional)</label>
              <input
                type="text"
                className="sim-field-input"
                placeholder="Reason for advance or field inspection notes..."
                value={transitionNote}
                onChange={(e) => setTransitionNote(e.target.value)}
              />
            </div>

            <div className="confirm-dialog-actions">
              <button
                type="button"
                className="btn-dialog-cancel"
                onClick={() => setConfirmModalOpen(false)}
                disabled={workflowActionLoading}
              >
                CANCEL
              </button>
              <button
                type="button"
                className="btn-dialog-confirm"
                onClick={handleExecuteTransition}
                disabled={workflowActionLoading}
              >
                {workflowActionLoading ? 'RECORDING TRANSITION...' : 'CONFIRM & ADVANCE'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CITIZEN ACCEPT RESOLUTION MODAL */}
      {acceptModalOpen && (
        <div className="confirm-dialog-overlay" role="dialog" aria-modal="true" aria-labelledby="accept-resolution-title">
          <div className="confirm-dialog-box crosshair-corner animate-fade-in">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <CheckCircle2 size={18} color="var(--civic-emerald)" />
              <h3 id="accept-resolution-title" style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-primary)' }}>
                Confirm Citizen Resolution & Close Case
              </h3>
            </div>

            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              Are you satisfied that the civic issue on docket <strong>{projection?.case_id}</strong> has been resolved?
              Accepting will transition the case directly to <strong style={{ color: 'var(--civic-emerald)' }}>RESOLVED</strong>.
              This decision is final and recorded in the append-only audit trail.
            </div>

            {resolutionActionError && (
              <div className="tracking-alert-card" role="alert" style={{ margin: '0.5rem 0' }}>
                <AlertCircle size={14} />
                <div style={{ fontSize: '0.8rem' }}>{resolutionActionError}</div>
              </div>
            )}

            <div className="sim-field-group">
              <label className="sim-field-label">Citizen Feedback (Optional)</label>
              <input
                type="text"
                className="sim-field-input"
                placeholder="Share any comments on the resolution quality..."
                value={citizenFeedback}
                onChange={(e) => setCitizenFeedback(e.target.value)}
                disabled={resolutionActionLoading}
              />
            </div>

            <div className="confirm-dialog-actions">
              <button
                type="button"
                className="btn-dialog-cancel"
                onClick={() => setAcceptModalOpen(false)}
                disabled={resolutionActionLoading}
              >
                CANCEL
              </button>
              <button
                type="button"
                className="btn-dialog-confirm"
                style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}
                onClick={handleAcceptResolution}
                disabled={resolutionActionLoading}
              >
                {resolutionActionLoading ? 'CONFIRMING CLOSURE...' : 'CONFIRM RESOLUTION & CLOSE'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CITIZEN REJECT RESOLUTION MODAL */}
      {rejectModalOpen && (
        <div className="confirm-dialog-overlay" role="dialog" aria-modal="true" aria-labelledby="reject-resolution-title">
          <div className="confirm-dialog-box crosshair-corner animate-fade-in">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <XCircle size={18} color="#f87171" />
              <h3 id="reject-resolution-title" style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-primary)' }}>
                Reject Resolution & Request Rework
              </h3>
            </div>

            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              Please explain what remains unresolved on docket <strong>{projection?.case_id}</strong>.
              The case will remain <strong style={{ color: 'var(--civic-amber)' }}>UNDER_REVIEW</strong> and the municipal department will be notified for corrective action.
            </div>

            {resolutionActionError && (
              <div className="tracking-alert-card" role="alert" style={{ margin: '0.5rem 0' }}>
                <AlertCircle size={14} />
                <div style={{ fontSize: '0.8rem' }}>{resolutionActionError}</div>
              </div>
            )}

            <div className="sim-field-group">
              <label className="sim-field-label">
                Substantive Rejection Reason <span style={{ color: '#f87171' }}>* (Minimum 5 characters)</span>
              </label>
              <textarea
                className="sim-field-input"
                style={{ minHeight: '80px', resize: 'vertical' }}
                placeholder="Explain why the resolution is incomplete or unsatisfactory..."
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                disabled={resolutionActionLoading}
              />
              <div style={{ fontSize: '0.72rem', color: rejectionReason.trim().length >= 5 ? 'var(--civic-emerald)' : 'var(--text-dim)' }}>
                {rejectionReason.trim().length}/5 characters minimum
              </div>
            </div>

            <div className="confirm-dialog-actions">
              <button
                type="button"
                className="btn-dialog-cancel"
                onClick={() => setRejectModalOpen(false)}
                disabled={resolutionActionLoading}
              >
                CANCEL
              </button>
              <button
                type="button"
                className="btn-dialog-confirm"
                style={{ background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)' }}
                onClick={handleRejectResolution}
                disabled={resolutionActionLoading || rejectionReason.trim().length < 5}
              >
                {resolutionActionLoading ? 'SUBMITTING REJECTION...' : 'REJECT RESOLUTION'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
