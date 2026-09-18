import React, { useState, useEffect } from 'react';
import { X, Building2, MapPin, AlertCircle, ShieldAlert, Check, ArrowRight, Paperclip, AlertTriangle } from 'lucide-react';
import { CanonicalCivicState, CivicCaseCreateRequest, ControlledDepartment } from '../../types/civic';
import './ActionDocketModal.css';

interface ActionDocketModalProps {
  isOpen: boolean;
  state: CanonicalCivicState | null;
  onClose: () => void;
  onSubmitCase: (payload: CivicCaseCreateRequest) => Promise<void>;
}

export const ActionDocketModal: React.FC<ActionDocketModalProps> = ({
  isOpen,
  state,
  onClose,
  onSubmitCase,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Accessibility: Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !state) return null;

  const handleSubmit = async () => {
    if (!state.description || !state.location) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const payload: CivicCaseCreateRequest = {
        description: state.description,
        location: state.location,
        department: state.department || ControlledDepartment.DRAINAGE_STORMWATER,
        pincode: state.pincode || null,
        is_public: true,
        latitude: state.latitude || null,
        longitude: state.longitude || null,
        location_source: state.location_source || null,
      };

      await onSubmitCase(payload);
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to create civic docket.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const deptLabel = state.department
    ? state.department.replace(/_/g, ' ')
    : 'DRAINAGE STORMWATER';

  return (
    <div className="docket-overlay" role="dialog" aria-modal="true" aria-labelledby="docket-record-title">
      <div className="docket-record-sheet crosshair-corner">
        {/* Archival Record Header */}
        <div className="docket-sheet-header">
          <div className="docket-header-meta">
            <div className="docket-stamp-tag">AI-GENERATED // ARCHIVAL RECORD</div>
            <div className="technical-label" style={{ color: 'var(--civic-cyan)', marginBottom: '4px' }}>
              AI-generated civic grievance record
            </div>
            <h2 id="docket-record-title" className="docket-sheet-title">
              CIVIC ACTION DOCKET
            </h2>
            <div className="docket-case-identifier">
              <span className="technical-label">DRAFT CASE REF:</span>
              <span className="case-ref-code">NS-CHN-2026-821F-PREVIEW</span>
            </div>
            <div className="docket-sub-clause">
              Generates an AI-generated Civic Action Docket draft with server-side validation.
            </div>
          </div>
          <button
            type="button"
            className="btn-sheet-close"
            onClick={onClose}
            aria-label="Close docket review modal"
          >
            <X size={18} />
          </button>
        </div>

        {submitError && (
          <div className="docket-alert-banner" role="alert">
            <AlertCircle size={14} />
            <span>{submitError}</span>
          </div>
        )}

        {/* Structured Civic Parameters Hierarchy */}
        <div className="docket-sheet-body">
          {/* 1. ISSUE */}
          <div className="record-section-block">
            <div className="section-block-label">
              <span className="technical-label">1. CIVIC ISSUE</span>
            </div>
            <div className="record-grid">
              <div className="record-cell">
                <span className="record-key">DEFECT CLASSIFICATION</span>
                <div className="record-val highlight">
                  {state.intent ? state.intent.replace(/_/g, ' ') : 'MUNICIPAL DEFECT'}
                </div>
              </div>
              <div className="record-cell">
                <span className="record-key">CONFIDENCE LEVEL</span>
                <div className="record-val">
                  {Math.round((state.confidence || 0.9) * 100)}% AI Confidence
                </div>
              </div>
            </div>
            <div className="statement-quote-box">
              <div className="statement-sub-label">CITIZEN GRIEVANCE STATEMENT</div>
              {state.description}
            </div>
          </div>

          {/* 2. LOCATION */}
          <div className="record-section-block">
            <div className="section-block-label">
              <span className="technical-label">2. LOCATION</span>
            </div>
            <div className="record-grid">
              <div className="record-cell">
                <span className="record-key">LOCATION</span>
                <div className="record-val" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <MapPin size={13} color="var(--civic-cyan)" />
                  <span>{state.location || 'UNSPECIFIED'}</span>
                </div>
              </div>
              <div className="record-cell">
                <span className="record-key">LANDMARK // PINCODE</span>
                <div className="record-val">
                  {state.landmark ? `${state.landmark} • ` : ''}PIN: {state.pincode || 'Unspecified'}
                </div>
              </div>
            </div>
          </div>

          {/* 3. ROUTING */}
          <div className="record-section-block">
            <div className="section-block-label">
              <span className="technical-label">3. ROUTING</span>
            </div>
            <div className="record-grid">
              <div className="record-cell">
                <span className="record-key">Recommended Department</span>
                <div className="record-val" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Building2 size={13} color="var(--civic-blue-hover)" />
                  <span>{deptLabel}</span>
                </div>
              </div>
              <div className="record-cell">
                <span className="record-key">ROUTING CONTEXT</span>
                <div className="record-val">Municipal Corporation (Recommended Routing)</div>
              </div>
            </div>
          </div>

          {/* 4. URGENCY */}
          <div className="record-section-block">
            <div className="section-block-label">
              <span className="technical-label">4. URGENCY</span>
            </div>
            <div className="record-grid">
              <div className="record-cell">
                <span className="record-key">ASSESSED URGENCY</span>
                <div className="record-val">
                  <span className="technical-tag">{state.urgency || 'MEDIUM'}</span>
                </div>
              </div>
              <div className="record-cell">
                <span className="record-key">URGENCY RATIONALE</span>
                <div className="record-val">
                  {state.urgency_rationale || 'Assessed based on municipal safety and pedestrian impact.'}
                </div>
              </div>
            </div>
          </div>

          {/* 5. EVIDENCE */}
          <div className="record-section-block">
            <div className="section-block-label">
              <span className="technical-label">5. EVIDENCE ATTACHMENTS</span>
            </div>
            <div className="evidence-placeholder-box">
              <Paperclip size={14} color="var(--text-muted)" />
              <span>
                Evidence can be attached immediately after docket creation via the Evidence Studio.
              </span>
            </div>
          </div>

          {/* Non-official government notice */}
          <div className="record-disclaimer-box" role="note">
            <div className="disclaimer-header-row">
              <ShieldAlert size={14} />
              <span>TRANSPARENT CIVIC NOTICE</span>
            </div>
            <p className="disclaimer-body">
              This record is generated by JARVIS Civic and is not proof of official government submission or resolution.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="docket-sheet-footer">
          <div className="footer-status-cue">
            <span className="cue-dot" />
            <span className="cue-text">READY FOR CASE CREATION</span>
          </div>

          <div className="footer-button-group">
            <button
              type="button"
              className="btn-docket-back"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Return to Interview
            </button>
            <button
              type="button"
              className="btn-docket-confirm"
              onClick={handleSubmit}
              disabled={isSubmitting || !state.description || !state.location}
              aria-label="Create Civic Action Docket"
            >
              <span>CREATE CIVIC ACTION DOCKET</span>
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
