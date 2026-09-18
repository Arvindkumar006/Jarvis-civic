import React, { useState, useEffect } from 'react';
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
} from 'lucide-react';
import {
  ApplicationRole,
  AuditEvent,
  CaseHistoryItem,
  CaseStatus,
  CivicCaseRecord,
  ControlledDepartment,
  PublicTrackingProjection,
} from '../../types/civic';
import { auditApi, casesApi, trackingApi } from '../../services/api';
import { CivicMap, getApproxCoordinates, MapMarkerItem } from '../Map/CivicMap';
import './TrackingView.css';

interface TrackingViewProps {
  initialCaseId?: string;
  recentCaseIds?: string[];
  onSelectCaseForEvidence?: (caseId: string) => void;
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
  [CaseStatus.UNDER_REVIEW]: {
    nextStatus: CaseStatus.RESOLVED,
    label: 'RECORD RESOLUTION',
    actionDesc: 'Certify civic work completion and record workflow resolution.',
  },
  [CaseStatus.RESOLVED]: null,
};

export const TrackingView: React.FC<TrackingViewProps> = ({
  initialCaseId = '',
  recentCaseIds = [],
  onSelectCaseForEvidence,
}) => {
  // Mode selection
  const [activeMode, setActiveMode] = useState<TrackingMode>('PUBLIC');

  // Input & Query State
  const [caseIdInput, setCaseIdInput] = useState(initialCaseId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projection, setProjection] = useState<PublicTrackingProjection | null>(null);
  const [caseRecord, setCaseRecord] = useState<CivicCaseRecord | null>(null);
  const [copied, setCopied] = useState(false);

  // Simulated Actor State (Frontend Evaluation / Test Mode only)
  const [simulatedRole, setSimulatedRole] = useState<ApplicationRole>(ApplicationRole.AUTHORITY_OFFICER);
  const [simulatedPrincipalId, setSimulatedPrincipalId] = useState('officer-drainage-1');
  const [simulatedDept, setSimulatedDept] = useState<ControlledDepartment>(ControlledDepartment.DRAINAGE_STORMWATER);

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
      if (e.key === 'Escape' && confirmModalOpen) {
        setConfirmModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmModalOpen]);

  // Adjust simulated defaults when role changes
  const handleRoleChange = (newRole: ApplicationRole) => {
    setSimulatedRole(newRole);
    if (newRole === ApplicationRole.AUTHORITY_OFFICER) {
      setSimulatedPrincipalId('officer-drainage-1');
      setSimulatedDept(ControlledDepartment.DRAINAGE_STORMWATER);
    } else if (newRole === ApplicationRole.MUNICIPAL_SUPERVISOR) {
      setSimulatedPrincipalId('sup-chennai-1');
      setSimulatedDept(ControlledDepartment.DRAINAGE_STORMWATER);
    } else if (newRole === ApplicationRole.ADMINISTRATOR) {
      setSimulatedPrincipalId('admin-sys-1');
    } else if (newRole === ApplicationRole.CITIZEN) {
      setSimulatedPrincipalId('cit-user-1');
    } else {
      setSimulatedPrincipalId('anon-public');
    }
  };

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

  // Load supplemental case details & audit events based on current actor
  const loadSupplementalData = async (caseId: string, _currentStatus?: string) => {
    // Try loading case details (succeeds if authorized)
    try {
      const fullCase = await casesApi.getCase(
        caseId,
        simulatedRole,
        simulatedPrincipalId,
        simulatedDept
      );
      setCaseRecord(fullCase);
    } catch {
      setCaseRecord(null);
    }

    // Try loading sanitized history
    try {
      const hist = await casesApi.getHistory(
        caseId,
        simulatedRole,
        simulatedPrincipalId,
        simulatedDept
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

  // Fetch Audit Trail with Cedar fail-closed evaluation
  const fetchAuditTrail = async (caseId: string) => {
    setAuditLoading(true);
    setAuditRestricted(false);
    try {
      const events = await auditApi.getCaseAuditTrail(
        caseId,
        simulatedRole,
        simulatedPrincipalId,
        simulatedDept
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

  // Re-fetch audit when mode switches to AUDIT or simulated actor changes
  useEffect(() => {
    if (projection && activeMode === 'AUDIT') {
      fetchAuditTrail(projection.case_id);
    }
  }, [activeMode, simulatedRole, simulatedDept, simulatedPrincipalId]);

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
    setWorkflowSuccessMsg(null);

    try {
      const updated = await casesApi.updateStatus(
        projection.case_id,
        {
          status: nextTransition.nextStatus,
          note: transitionNote.trim() || undefined,
        },
        simulatedRole,
        simulatedPrincipalId,
        simulatedDept
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
        simulatedRole,
        simulatedPrincipalId,
        simulatedDept
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
    simulatedRole === ApplicationRole.AUTHORITY_OFFICER &&
    simulatedDept !== projection.recommended_department;

  return (
    <div className="civic-tracking-view crosshair-corner" aria-label="Civic Action Journey">
      {/* Header Bar */}
      <div className="tracking-header-block">
        <div className="tracking-prehead">
          <span className="technical-label">CIVIC CASE WORKSPACE // AUTHORITY & AUDIT TRAIL</span>
        </div>
        <h2 className="tracking-view-title">Track Civic Action Docket</h2>
        <p className="tracking-view-sub">
          Verify public tracking progression, execute authorized authority status transitions, and inspect Cedar-protected audit logs.
        </p>
      </div>

      {/* THREE-MODE SELECTOR TABS */}
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
      </div>

      {/* SIMULATED ACTOR CONSOLE (Shown in Authority & Audit Modes) */}
      {(activeMode === 'AUTHORITY' || activeMode === 'AUDIT') && (
        <div className="simulation-control-strip animate-fade-in" role="region" aria-label="Simulated Actor Console">
          <div className="simulation-top-row">
            <div className="simulation-badge">
              <Sliders size={12} />
              <span>SIMULATED AUTHORITY CONTEXT</span>
            </div>
            <span className="simulation-notice">
              Frontend actor controls are for local testing only. Server-side Cedar PEP determines authoritative authorization.
            </span>
          </div>

          <div className="simulation-fields-grid">
            <div className="sim-field-group">
              <label className="sim-field-label">Simulated Role</label>
              <select
                className="sim-field-select"
                value={simulatedRole}
                onChange={(e) => handleRoleChange(e.target.value as ApplicationRole)}
              >
                <option value={ApplicationRole.AUTHORITY_OFFICER}>AUTHORITY OFFICER (Departmental)</option>
                <option value={ApplicationRole.MUNICIPAL_SUPERVISOR}>MUNICIPAL SUPERVISOR (Departmental)</option>
                <option value={ApplicationRole.ADMINISTRATOR}>ADMINISTRATOR (Universal)</option>
                <option value={ApplicationRole.CITIZEN}>CITIZEN (Restricted)</option>
                <option value={ApplicationRole.PUBLIC}>PUBLIC (Anonymous)</option>
              </select>
            </div>

            {(simulatedRole === ApplicationRole.AUTHORITY_OFFICER ||
              simulatedRole === ApplicationRole.MUNICIPAL_SUPERVISOR) && (
              <div className="sim-field-group">
                <label className="sim-field-label">Assigned Department</label>
                <select
                  className="sim-field-select"
                  value={simulatedDept}
                  onChange={(e) => setSimulatedDept(e.target.value as ControlledDepartment)}
                >
                  <option value={ControlledDepartment.DRAINAGE_STORMWATER}>DRAINAGE_STORMWATER</option>
                  <option value={ControlledDepartment.PWD_ROADS}>PWD_ROADS</option>
                  <option value={ControlledDepartment.MUNICIPAL_CORPORATION}>MUNICIPAL_CORPORATION</option>
                  <option value={ControlledDepartment.WASTE_MANAGEMENT}>WASTE_MANAGEMENT</option>
                  <option value={ControlledDepartment.WATER_SUPPLY}>WATER_SUPPLY</option>
                  <option value={ControlledDepartment.ELECTRICITY_UTILITY}>ELECTRICITY_UTILITY</option>
                  <option value={ControlledDepartment.OTHER_MANUAL_REVIEW}>OTHER_MANUAL_REVIEW</option>
                </select>
              </div>
            )}

            <div className="sim-field-group">
              <label className="sim-field-label">Principal ID</label>
              <input
                type="text"
                className="sim-field-input"
                value={simulatedPrincipalId}
                onChange={(e) => setSimulatedPrincipalId(e.target.value)}
              />
            </div>
          </div>
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
                      Case is assigned to <strong>{projection.recommended_department}</strong>, but current actor is simulated as <strong>{simulatedDept}</strong>.
                      Cedar Policy will reject workflow mutations under fail-closed departmental scoping. Change simulated department above to match the case.
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
                      {nextTransition ? nextTransition.nextStatus.replace(/_/g, ' ') : 'LIFECYCLE COMPLETED'}
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
                ) : (
                  <div style={{ fontSize: '0.8rem', color: 'var(--civic-emerald)', fontStyle: 'italic' }}>
                    ✓ This case has reached final resolution (RESOLVED). No further forward transitions are possible.
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
                    The current simulated principal (<strong>{simulatedRole}</strong>) lacks permission to execute <code>read_audit_log</code> on this case.
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
    </div>
  );
};
