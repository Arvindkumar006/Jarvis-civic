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
} from 'lucide-react';
import { PublicTrackingProjection } from '../../types/civic';
import { trackingApi } from '../../services/api';
import { CivicMap, getApproxCoordinates, MapMarkerItem } from '../Map/CivicMap';
import './TrackingView.css';

interface TrackingViewProps {
  initialCaseId?: string;
  recentCaseIds?: string[];
  onSelectCaseForEvidence?: (caseId: string) => void;
}

interface JourneyStep {
  step: number;
  label: string;
  code: string;
  desc: string;
}

const CANONICAL_JOURNEY: JourneyStep[] = [
  { step: 1, label: 'Docket Created', code: 'DOCKET_CREATED', desc: 'Civic grievance verified and structured into record.' },
  { step: 2, label: 'Routing Prepared', code: 'ROUTING_PREPARED', desc: 'Routing prepared for the recommended department.' },
  { step: 3, label: 'Submission Ready', code: 'SUBMISSION_READY', desc: 'Prepared for potential authority intake.' },
  { step: 4, label: 'Under Review', code: 'UNDER_REVIEW', desc: 'Authority review stage.' },
  { step: 5, label: 'Resolved', code: 'RESOLVED', desc: 'Resolution recorded in the civic workflow.' },
];

export const TrackingView: React.FC<TrackingViewProps> = ({
  initialCaseId = '',
  recentCaseIds = [],
  onSelectCaseForEvidence,
}) => {
  const [caseIdInput, setCaseIdInput] = useState(initialCaseId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projection, setProjection] = useState<PublicTrackingProjection | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (initialCaseId && initialCaseId.trim().length > 0) {
      setCaseIdInput(initialCaseId);
      handleTrack(initialCaseId.trim());
    }
  }, [initialCaseId]);

  const handleTrack = async (targetId: string) => {
    const id = targetId.trim();
    if (!id) {
      setError('Please enter a valid Case ID.');
      return;
    }

    setLoading(true);
    setError(null);
    setProjection(null);

    try {
      const data = await trackingApi.getTracking(id);
      setProjection(data);
    } catch (err: any) {
      setError(err.message || 'Unable to retrieve case tracking record. Please verify the Case ID.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyId = () => {
    if (projection?.case_id) {
      navigator.clipboard.writeText(projection.case_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getStatusStepIndex = (status: string) => {
    const s = status.toUpperCase().replace(/\s+/g, '_');
    if (s === 'DRAFT' || s === 'DOCKET_CREATED') return 1;
    if (s === 'TRIAGED' || s === 'ROUTING_PREPARED') return 2;
    if (s === 'SUBMISSION_READY') return 3;
    if (s === 'ASSIGNED' || s === 'IN_PROGRESS' || s === 'UNDER_REVIEW') return 4;
    if (s === 'RESOLVED') return 5;
    return 1;
  };

  const currentStep = projection ? getStatusStepIndex(projection.status) : 0;

  // Derive coordinates if case has known reference or location
  const approxCoords = projection ? getApproxCoordinates(projection.case_id) : null;
  const caseMarkers: MapMarkerItem[] = approxCoords && projection
    ? [
        {
          id: projection.case_id,
          lat: approxCoords[0],
          lng: approxCoords[1],
          category: 'WATER',
          title: `Case ${projection.case_id}`,
          subtitle: `Recommended Dept: ${projection.recommended_department}`,
          department: projection.recommended_department,
          urgency: 'Medium',
          status: projection.status,
        },
      ]
    : [];

  return (
    <div className="civic-tracking-view crosshair-corner" aria-label="Civic Action Journey">
      {/* Header Bar */}
      <div className="tracking-header-block">
        <div className="tracking-prehead">
          <span className="technical-label">CIVIC CASE INTELLIGENCE WORKSPACE // PUBLIC-SAFE TRACKING</span>
        </div>
        <h2 className="tracking-view-title">Track Civic Action Docket</h2>
        <p className="tracking-view-sub">
          Follow the lifecycle of your AI-generated Civic Action Docket. Projections strictly protect citizen privacy.
        </p>
      </div>

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

      {/* Search Bar Console */}
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

      {error && (
        <div className="tracking-alert-card" role="alert">
          <AlertCircle size={16} />
          <div>
            <div className="alert-title">Case Lookup Failed</div>
            <div className="alert-body">{error}</div>
          </div>
        </div>
      )}

      {/* Empty State: Standby Mode */}
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

      {/* CASE INTELLIGENCE WORKSPACE: Case Selected */}
      {projection && (
        <div className="case-intelligence-workspace animate-fade-in">
          {/* Top Case Identity & Telemetry Strip */}
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

          {/* Split Layout: Left Lifecycle Journey, Right Case Map & Telemetry */}
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

              {/* Case Map Visualization */}
              <div className="case-map-frame">
                <CivicMap
                  center={approxCoords || [13.0604, 80.2496]}
                  zoom={approxCoords ? 14 : 12}
                  markers={caseMarkers}
                  interactive={true}
                  allowManualPin={false}
                  locationName="Civic Landmark Reference"
                  className="tracking-case-leaflet-map"
                />
              </div>

              <div className="case-spatial-note">
                <span className="note-icon">ℹ</span>
                <span>
                  Public tracking projections disclose verified departmental routing and sanitized timestamps.
                  Exact physical GPS coordinates are withheld from unauthenticated queries to protect citizen privacy.
                </span>
              </div>
            </div>
          </div>

          {/* Transparent Civic Notice */}
          <div className="record-disclaimer-box" role="note" style={{ marginTop: '1.25rem' }}>
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
    </div>
  );
};

