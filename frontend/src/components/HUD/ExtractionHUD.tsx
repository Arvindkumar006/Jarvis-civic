import React from 'react';
import {
  MapPin,
  ArrowRight,
  CheckCircle2,
  Building2,
  AlertTriangle,
  Globe,
  Compass,
} from 'lucide-react';
import { CanonicalCivicState, UrgencyLevel } from '../../types/civic';
import './ExtractionHUD.css';

interface ExtractionHUDProps {
  state: CanonicalCivicState | null;
  isLoading?: boolean;
  onOpenDocketModal?: () => void;
  onOpenDocketReview?: () => void;
}

const DEPARTMENT_LABELS: Record<string, string> = {
  DRAINAGE_STORMWATER: 'Drainage & Stormwater',
  ROADS_BRIDGES: 'Roads & Bridges',
  PWD_ROADS: 'PWD / Roads',
  ELECTRICAL_LIGHTING: 'Electrical / Streetlights',
  SOLID_WASTE: 'Solid Waste Management',
  TRAFFIC_POLICE: 'Traffic Enforcement',
  MUNICIPAL_ADMIN: 'Municipal Administration',
};

export const ExtractionHUD: React.FC<ExtractionHUDProps> = ({
  state,
  isLoading = false,
  onOpenDocketModal,
  onOpenDocketReview,
}) => {
  const triggerReview = onOpenDocketReview || onOpenDocketModal;
  const hasIntent = Boolean(state?.intent);
  const hasLocation = Boolean(state?.location);
  const hasDept = Boolean(state?.department);
  const hasUrgency = Boolean(state?.urgency);
  const isReady = state?.ready_for_action ?? Boolean(state?.description && state?.location);
  const confidencePercent = state?.confidence ? Math.round(state.confidence * 100) : 0;
  const deptLabel = state?.department
    ? DEPARTMENT_LABELS[state.department] || state.department.replace(/_/g, ' ')
    : 'Pending analysis';

  const urgencyColor =
    state?.urgency === UrgencyLevel.CRITICAL
      ? 'var(--civic-rose)'
      : state?.urgency === UrgencyLevel.HIGH
      ? 'var(--civic-amber)'
      : state?.urgency === UrgencyLevel.MEDIUM
      ? 'var(--civic-blue-hover)'
      : 'var(--text-muted)';

  const activeLang = state?.citizen_language || (state as any)?.language || null;

  return (
    <aside className="civic-signal-panel crosshair-corner" aria-label="Civic Signal Telemetry">
      {/* Animated Scan Line */}
      <div className="signal-scan-beam" aria-hidden="true" />

      {/* Header */}
      <div className="signal-header">
        <div className="signal-brand-row">
          <div className="signal-pulse-orb" />
          <span className="signal-heading">Civic Extraction HUD</span>
          <span className="signal-mode-tag">LIVE EXTRACTION</span>
        </div>
        <div className="signal-subhead-row">
          <span className="technical-label">AI CIVIC REASONING HUD</span>
        </div>
        <div className={`signal-system-state ${isReady ? 'state-ready' : 'state-active'}`}>
          <span className="state-bullet" />
          <span>{isReady ? 'CIVIC SIGNAL VALIDATED' : isLoading ? 'ANALYZING CIVIC SIGNAL' : hasIntent ? 'ANALYZING CIVIC SIGNAL' : 'WAITING FOR CIVIC SIGNAL — Listening for problem statement'}</span>
        </div>
      </div>

      <div className="signal-body">
        {/* Issue Progressive Field */}
        <div className="signal-section">
          <div className="signal-label-row">
            <div className="prog-indicator-wrap">
              {hasIntent ? (
                <span className="prog-icon check">✓</span>
              ) : isLoading ? (
                <span className="prog-icon detecting">◉</span>
              ) : (
                <span className="prog-icon awaiting">○</span>
              )}
              <span className="signal-field-label">ISSUE</span>
            </div>
            <span className="signal-field-code">CIVIC_INTENT</span>
          </div>
          <div className="signal-value-block">
            {state?.intent ? (
              <span className="signal-intent-badge">
                {state.intent.replace(/_/g, ' ')}
              </span>
            ) : (
              <span className="signal-placeholder">
                {isLoading ? 'Detecting civic defect...' : 'Awaiting input'}
              </span>
            )}
          </div>
        </div>

        {/* Location Progressive Field */}
        <div className="signal-section">
          <div className="signal-label-row">
            <div className="prog-indicator-wrap">
              {hasLocation ? (
                <span className="prog-icon check">✓</span>
              ) : isLoading ? (
                <span className="prog-icon detecting">◉</span>
              ) : (
                <span className="prog-icon awaiting">○</span>
              )}
              <span className="signal-field-label">LOCATION</span>
            </div>
            <span className="signal-field-code">TEXTUAL_REF</span>
          </div>
          <div className="signal-value-block">
            <div className="signal-location-row">
              <MapPin size={13} color="var(--civic-cyan)" />
              <span className="signal-location-text">
                {state?.location || (isLoading ? 'Detecting location...' : 'Awaiting location reference')}
              </span>
            </div>
            {state?.landmark && (
              <div className="signal-landmark-tag">
                <span>Landmark:</span> <strong>{state.landmark}</strong>
              </div>
            )}
            {state?.pincode && (
              <div className="signal-pincode-tag">
                <span>PIN:</span> <strong>{state.pincode}</strong>
              </div>
            )}
          </div>
        </div>

        {/* Recommended Department Field */}
        <div className="signal-section">
          <div className="signal-label-row">
            <div className="prog-indicator-wrap">
              {hasDept ? (
                <span className="prog-icon check">✓</span>
              ) : isLoading ? (
                <span className="prog-icon detecting">◉</span>
              ) : (
                <span className="prog-icon awaiting">○</span>
              )}
              <span className="signal-field-label">RECOMMENDED DEPARTMENT</span>
            </div>
            <span className="signal-field-code">JURISDICTION</span>
          </div>
          <div className="signal-value-block">
            <div className="signal-dept-row">
              <Building2 size={13} className="signal-icon-dim" />
              <span className="signal-dept-name">{deptLabel}</span>
            </div>
          </div>
        </div>

        {/* Telemetry Matrix (Urgency, Language, Confidence) */}
        <div className="signal-matrix-row">
          {/* Urgency */}
          <div className="signal-matrix-cell">
            <div className="matrix-label-with-prog">
              {hasUrgency ? <span className="prog-mini-check">✓</span> : <span className="prog-mini-dim">○</span>}
              <span className="signal-field-label">URGENCY</span>
            </div>
            <div className="signal-urgency-val" style={{ color: urgencyColor }}>
              <span className="urgency-dot" style={{ background: urgencyColor }} />
              <span>{state?.urgency || 'MEDIUM'}</span>
            </div>
          </div>

          {/* Language */}
          <div className="signal-matrix-cell">
            <span className="signal-field-label">LANGUAGE</span>
            <div className="signal-meta-val">
              <Globe size={11} color="var(--civic-cyan)" />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }}>
                {activeLang || 'Auto-detect'}
              </span>
            </div>
          </div>

          {/* Confidence */}
          <div className="signal-matrix-cell">
            <span className="signal-field-label">AI CONFIDENCE</span>
            <div className="signal-confidence-val">
              <div className="confidence-track-mini">
                <div
                  className="confidence-fill-mini"
                  style={{ width: `${confidencePercent || 0}%` }}
                />
              </div>
              <span className="confidence-num">{confidencePercent}%</span>
            </div>
          </div>
        </div>

        {/* Missing Information Checklist */}
        {state && state.missing_fields && state.missing_fields.length > 0 && !isReady && (
          <div className="signal-missing-group" role="region" aria-label="Missing Signals">
            <div className="missing-group-header">
              <AlertTriangle size={12} color="var(--civic-amber)" />
              <span className="missing-group-title">MISSING INFORMATION</span>
            </div>
            <div className="missing-signals-list">
              {state.missing_fields.map((field) => (
                <div key={field} className="missing-signal-line">
                  <span className="unresolved-circle">○</span>
                  <span className="missing-text">
                    Please specify: <strong>{field.replace(/_/g, ' ')}</strong>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Ready For Action Transformation Section */}
        {isReady && (
          <div className="signal-ready-banner animate-fade-in" role="status">
            <div className="ready-divider-line" />
            <div className="ready-status-row">
              <CheckCircle2 size={16} color="var(--civic-emerald)" />
              <span className="ready-title">CIVIC SIGNAL VALIDATED</span>
            </div>

            <div className="validated-checklist-grid">
              <div className="valid-item">✓ ISSUE</div>
              <div className="valid-item">✓ LOCATION</div>
              <div className="valid-item">✓ RECOMMENDED DEPARTMENT</div>
              <div className="valid-item">✓ URGENCY</div>
              <div className="valid-item">✓ LANGUAGE</div>
            </div>

            <div className="ready-callout-text">READY FOR ACTION</div>

            {triggerReview && (
              <button
                type="button"
                className="btn-create-civic-docket btn-review-docket-action illuminated"
                onClick={triggerReview}
                aria-label="Review & Generate Docket"
              >
                <span>CREATE CIVIC ACTION DOCKET →</span>
              </button>
            )}

            <p className="ready-disclaimer-text">
              This record is generated by JARVIS Civic and is not proof of official government submission or resolution.
            </p>
          </div>
        )}
      </div>

      {/* Footer Meta */}
      <div className="signal-footer">
        <span className="signal-footer-rule" />
        <span className="signal-footer-text">SECURED BY CEDAR PEP • FAIL-CLOSED GUARANTEE</span>
      </div>
    </aside>
  );
};
