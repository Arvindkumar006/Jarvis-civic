import React from 'react';
import {
  Building2,
  ShieldCheck,
  Search,
  ArrowRight,
  ShieldAlert,
  FileCheck2,
  Clock,
  Paperclip,
  CheckCircle2,
  Sliders,
  AlertTriangle,
} from 'lucide-react';
import { ApplicationRole, ControlledDepartment } from '../../types/civic';
import { useWorkspace } from '../../context/WorkspaceContext';
import './AuthorityConsole.css';

interface AuthorityConsoleProps {
  onNavigateToTrack: (caseId?: string) => void;
  onNavigateToEvidence: (caseId?: string) => void;
  onNavigateToAudit?: (caseId?: string) => void;
  recentCaseIds?: string[];
}

// Sample mock queue relevant to department workflows for authority triage
interface DepartmentDocketItem {
  id: string;
  issue: string;
  location: string;
  department: ControlledDepartment;
  status: string;
  urgency: 'MEDIUM' | 'HIGH' | 'CRITICAL';
  created: string;
}

const SAMPLE_DEPARTMENT_DOCKETS: DepartmentDocketItem[] = [
  {
    id: 'NS-CHN-2026-14CE',
    issue: 'Stormwater Drain Clogging & Silt Accumulation',
    location: 'Anna Salai near Thousand Lights',
    department: ControlledDepartment.DRAINAGE_STORMWATER,
    status: 'DOCKET_CREATED',
    urgency: 'HIGH',
    created: '2026-09-18 14:30',
  },
  {
    id: 'NS-CHN-2026-821F',
    issue: 'Hazardous Road Crater & Bitumen Fracture',
    location: 'MG Road Railway Bridge Approach',
    department: ControlledDepartment.PWD_ROADS,
    status: 'ROUTING_PREPARED',
    urgency: 'CRITICAL',
    created: '2026-09-18 11:15',
  },
  {
    id: 'NS-CHN-2026-4B90',
    issue: 'Consecutive Streetlight Cluster Blackout',
    location: '5th Main Road, Sector 4',
    department: ControlledDepartment.ELECTRICITY_UTILITY,
    status: 'SUBMISSION_READY',
    urgency: 'MEDIUM',
    created: '2026-09-17 19:40',
  },
  {
    id: 'NS-CHN-2026-5E2A',
    issue: 'Commercial Garbage Spillover & Silt Deposition',
    location: 'Velachery Bypass Market Junction',
    department: ControlledDepartment.WASTE_MANAGEMENT,
    status: 'UNDER_REVIEW',
    urgency: 'HIGH',
    created: '2026-09-17 08:20',
  },
  {
    id: 'NS-CHN-2026-9A10',
    issue: 'Potable Water Pipeline Pressure Deficit',
    location: 'T Nagar 3rd Cross Street',
    department: ControlledDepartment.WATER_SUPPLY,
    status: 'DOCKET_CREATED',
    urgency: 'MEDIUM',
    created: '2026-09-18 09:05',
  },
];

export const AuthorityConsole: React.FC<AuthorityConsoleProps> = ({
  onNavigateToTrack,
  onNavigateToEvidence,
  onNavigateToAudit,
  recentCaseIds = [],
}) => {
  const { session, switchWorkspace } = useWorkspace();
  const { role, department, principalId } = session;

  const isSupervisor = role === ApplicationRole.MUNICIPAL_SUPERVISOR;
  const isAdmin = role === ApplicationRole.ADMINISTRATOR;

  const [searchQuery, setSearchQuery] = React.useState('');
  const [searchResults, setSearchResults] = React.useState<any[] | null>(null);
  const [isSearching, setIsSearching] = React.useState(false);
  const [searchError, setSearchError] = React.useState<string | null>(null);
  const [searchedCount, setSearchedCount] = React.useState<number | null>(null);

  const handleDocketSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResults(null);
      setSearchedCount(null);
      return;
    }
    setIsSearching(true);
    setSearchError(null);
    try {
      const resp = await fetch(`/api/dockets/search?q=${encodeURIComponent(searchQuery.trim())}`, {
        credentials: 'include',
      });
      if (!resp.ok) {
        if (resp.status === 403) {
          throw new Error('Cedar Policy Denial: Unauthorized search scope');
        }
        if (resp.status === 503) {
          throw new Error('OpenSearch service is temporarily unavailable');
        }
        throw new Error(`Search error (${resp.status})`);
      }
      const data = await resp.json();
      setSearchResults(data.items || []);
      setSearchedCount(data.total || 0);
    } catch (err: any) {
      setSearchError(err.message || 'Search failed');
      setSearchResults([]);
      setSearchedCount(0);
    } finally {
      setIsSearching(false);
    }
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setSearchResults(null);
    setSearchError(null);
    setSearchedCount(null);
  };

  // Filter queue by department if authority/supervisor; show all if admin
  const relevantDockets = isAdmin
    ? SAMPLE_DEPARTMENT_DOCKETS
    : SAMPLE_DEPARTMENT_DOCKETS.filter(
        (d) => !department || d.department === department
      );

  // Fallback if no dockets match selected department
  const displayDockets =
    relevantDockets.length > 0
      ? relevantDockets
      : SAMPLE_DEPARTMENT_DOCKETS.slice(0, 2);

  return (
    <div className="authority-console-root animate-fade-in" aria-label="Authority Console Workspace">
      {/* Top Banner: Server-Authorized Civic Workspace */}
      <div className="console-hero-banner crosshair-corner">
        <div className="hero-banner-meta">
          <div className="hero-banner-tags">
            <span className="auth-badge-live">
              <ShieldCheck size={13} color="var(--civic-emerald)" />
              <span>SERVER-AUTHORIZED WORKSPACE</span>
            </span>
            <span className="cedar-policy-pill">CEDAR POLICY ENFORCEMENT ACTIVE</span>
          </div>

          <h1 className="hero-banner-title">
            {isAdmin
              ? 'Administrative Civic Control Plane'
              : isSupervisor
              ? 'Department Workflow Oversight'
              : 'Your Authorized Civic Workspace'}
          </h1>

          <p className="hero-banner-subtitle">
            {isAdmin
              ? 'Full cross-departmental lifecycle visibility and audit verification governed by server-side Cedar policies.'
              : isSupervisor
              ? `Departmental governance and authorized audit inspection for ${department ? department.replace(/_/g, ' ') : 'Municipal Operations'}.`
              : `Department-scoped civic action triage and status transitions for ${department ? department.replace(/_/g, ' ') : 'Municipal Operations'}.`}
          </p>

          <div className="hero-identity-strip">
            <div className="identity-cell">
              <span className="id-label">ACTIVE ROLE</span>
              <span className="id-value">{role.replace(/_/g, ' ')}</span>
            </div>
            {department && (
              <div className="identity-cell">
                <span className="id-label">DEPARTMENT SCOPE</span>
                <span className="id-value highlight-dept">{department.replace(/_/g, ' ')}</span>
              </div>
            )}
            <div className="identity-cell">
              <span className="id-label">LOCAL SIMULATION IDENTITY</span>
              <span className="id-value mono-id">{principalId}</span>
            </div>
            <button
              type="button"
              className="btn-switch-workspace-inline"
              onClick={switchWorkspace}
              title="Change active role or department"
            >
              SWITCH WORKSPACE
            </button>
          </div>
        </div>
      </div>

      {/* Metric Tiles Row */}
      <div className="console-metrics-row">
        <div className="metric-tile crosshair-corner">
          <div className="metric-top">
            <span className="technical-label">AUTHORIZED SCOPE</span>
            <Building2 size={15} color="var(--civic-cyan)" />
          </div>
          <div className="metric-main-val">
            {isAdmin ? 'ALL DEPARTMENTS' : department ? department.split('_')[0] : 'ASSIGNED'}
          </div>
          <div className="metric-sub">Fail-closed Cedar policy boundary</div>
        </div>

        <div className="metric-tile crosshair-corner">
          <div className="metric-top">
            <span className="technical-label">LIFECYCLE PIPELINE</span>
            <FileCheck2 size={15} color="var(--civic-amber)" />
          </div>
          <div className="metric-main-val">5 STAGES</div>
          <div className="metric-sub">Strict single-step forward progression</div>
        </div>

        <div className="metric-tile crosshair-corner">
          <div className="metric-top">
            <span className="technical-label">PENDING TRIAGE</span>
            <Clock size={15} color="var(--civic-emerald)" />
          </div>
          <div className="metric-main-val">{displayDockets.length} DOCKETS</div>
          <div className="metric-sub">Ready for departmental review</div>
        </div>

        <div className="metric-tile crosshair-corner">
          <div className="metric-top">
            <span className="technical-label">AUDIT ACCESS</span>
            <ShieldCheck size={15} color={isSupervisor || isAdmin ? 'var(--civic-emerald)' : 'var(--text-muted)'} />
          </div>
          <div className="metric-main-val">
            {isAdmin ? 'UNIVERSAL' : isSupervisor ? 'DEPT-SCOPED' : 'RESTRICTED'}
          </div>
          <div className="metric-sub">
            {isAdmin || isSupervisor ? 'Full append-only audit verification' : 'Read audit governed by supervisor'}
          </div>
        </div>
      </div>

      {/* Main Department Queue & Quick Action Grid */}
      <div className="console-content-grid">
        {/* Department Triage Queue */}
        <div className="console-queue-card crosshair-corner">
          <div className="queue-card-header">
            <div>
              <span className="technical-label">
                {searchResults !== null ? 'OPENSEARCH RESULTS // AUTHORIZED DOCKETS' : 'DEPARTMENT CIVIC QUEUE // ACTIVE DOCKETS'}
              </span>
              <h3 className="queue-title">
                {searchResults !== null ? 'OpenSearch Query Results' : 'Assigned Grievance Dockets'}
              </h3>
            </div>
            <span className="queue-filter-tag">
              {isAdmin ? 'UNIVERSAL JURISDICTION' : department || 'DEPARTMENTAL SCOPE'}
            </span>
          </div>

          {/* OpenSearch Query Input Bar */}
          <form className="queue-search-form" onSubmit={handleDocketSearch}>
            <div className="queue-search-input-wrapper">
              <Search size={14} className="queue-search-icon" />
              <input
                type="text"
                className="queue-search-input"
                placeholder={
                  isAdmin
                    ? "Search all dockets via OpenSearch (title, description, location, case_id)..."
                    : `Search ${department ? department.replace(/_/g, ' ') : 'assigned'} dockets via OpenSearch...`
                }
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="btn-clear-search"
                  onClick={handleClearSearch}
                  title="Clear search"
                >
                  ✕
                </button>
              )}
            </div>
            <button
              type="submit"
              className="btn-opensearch-submit"
              disabled={isSearching}
            >
              {isSearching ? 'SEARCHING...' : 'OPENSEARCH'}
            </button>
          </form>

          {searchError && (
            <div className="search-error-banner">
              <AlertTriangle size={14} />
              <span>{searchError}</span>
            </div>
          )}

          {searchResults !== null && (
            <div className="search-results-meta">
              <span>
                Found <strong>{searchedCount}</strong> authorized dockets in OpenSearch
              </span>
              <button
                type="button"
                className="btn-reset-view"
                onClick={handleClearSearch}
              >
                Reset to Default Queue
              </button>
            </div>
          )}

          <div className="queue-items-table" role="region" aria-label="Department Dockets Table">
            {searchResults !== null ? (
              searchResults.length === 0 ? (
                <div className="queue-empty-search">
                  No matching dockets found in OpenSearch for your authorized scope.
                </div>
              ) : (
                searchResults.map((item) => (
                  <div key={item.case_id} className="queue-row-item">
                    <div className="queue-row-main">
                      <div className="queue-row-top">
                        <span className="docket-code">{item.case_id}</span>
                        <span className="docket-status-badge">{item.status.replace(/_/g, ' ')}</span>
                      </div>
                      <div className="docket-issue-text">{item.title || item.description}</div>
                      <div className="docket-location-sub">
                        <span>{item.location}</span> • <span>{item.department.replace(/_/g, ' ')}</span> •{' '}
                        <span>{new Date(item.created_at).toLocaleString()}</span>
                      </div>
                    </div>

                    <div className="queue-row-actions">
                      <button
                        type="button"
                        className="btn-queue-action primary"
                        onClick={() => onNavigateToTrack(item.case_id)}
                        title={`Open tracking & workflow for ${item.case_id}`}
                      >
                        <Search size={12} />
                        <span>TRACK & TRANSITION</span>
                      </button>
                      <button
                        type="button"
                        className="btn-queue-action secondary"
                        onClick={() => onNavigateToEvidence(item.case_id)}
                        title={`Inspect evidence for ${item.case_id}`}
                      >
                        <Paperclip size={12} />
                        <span>EVIDENCE</span>
                      </button>
                    </div>
                  </div>
                ))
              )
            ) : (
              displayDockets.map((docket) => (
                <div key={docket.id} className="queue-row-item">
                  <div className="queue-row-main">
                    <div className="queue-row-top">
                      <span className="docket-code">{docket.id}</span>
                      <span className="docket-status-badge">{docket.status.replace(/_/g, ' ')}</span>
                      <span className={`urgency-pill ${docket.urgency.toLowerCase()}`}>
                        {docket.urgency} URGENCY
                      </span>
                    </div>
                    <div className="docket-issue-text">{docket.issue}</div>
                    <div className="docket-location-sub">
                      <span>{docket.location}</span> • <span>{docket.department.replace(/_/g, ' ')}</span> •{' '}
                      <span>{docket.created}</span>
                    </div>
                  </div>

                  <div className="queue-row-actions">
                    <button
                      type="button"
                      className="btn-queue-action primary"
                      onClick={() => onNavigateToTrack(docket.id)}
                      title={`Open tracking & workflow for ${docket.id}`}
                    >
                      <Search size={12} />
                      <span>TRACK & TRANSITION</span>
                    </button>
                    <button
                      type="button"
                      className="btn-queue-action secondary"
                      onClick={() => onNavigateToEvidence(docket.id)}
                      title={`Inspect evidence for ${docket.id}`}
                    >
                      <Paperclip size={12} />
                      <span>EVIDENCE</span>
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="queue-footer-tip">
            <span className="tip-bullet">●</span>
            <span>
              To execute authorized status transitions (e.g. <code>UNDER_REVIEW</code> &rarr;{' '}
              <code>RESOLVED</code>), click <strong>TRACK & TRANSITION</strong> above.
            </span>
          </div>
        </div>

        {/* Right Rail: Workflow Pipeline & Governance Info */}
        <div className="console-side-rail">
          {/* Canonical Workflow Stages Rail */}
          <div className="side-card crosshair-corner">
            <div className="side-card-header">
              <span className="technical-label">LIFECYCLE PROGRESSION</span>
              <h4 className="side-title">Canonical Workflow Sequence</h4>
            </div>

            <div className="canonical-steps-flow">
              <div className="flow-step-item">
                <span className="step-num">01</span>
                <div>
                  <strong>Docket Created</strong>
                  <p>Intake synthesized and Pydantic validated</p>
                </div>
              </div>
              <div className="flow-connector">↓</div>
              <div className="flow-step-item">
                <span className="step-num">02</span>
                <div>
                  <strong>Routing Prepared</strong>
                  <p>Assigned to competent municipal department</p>
                </div>
              </div>
              <div className="flow-connector">↓</div>
              <div className="flow-step-item">
                <span className="step-num">03</span>
                <div>
                  <strong>Submission Ready</strong>
                  <p>Verified evidence checklist & authority clearance</p>
                </div>
              </div>
              <div className="flow-connector">↓</div>
              <div className="flow-step-item">
                <span className="step-num">04</span>
                <div>
                  <strong>Under Review</strong>
                  <p>Active field triage & municipal investigation</p>
                </div>
              </div>
              <div className="flow-connector">↓</div>
              <div className="flow-step-item">
                <span className="step-num">05</span>
                <div>
                  <strong>Resolved</strong>
                  <p>Attributed resolution note & audit recording</p>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Jump / Inspection Actions */}
          <div className="side-card crosshair-corner">
            <div className="side-card-header">
              <span className="technical-label">WORKFLOW CONTROLS</span>
              <h4 className="side-title">Quick Navigation</h4>
            </div>

            <div className="side-actions-group">
              <button
                type="button"
                className="btn-quick-nav"
                onClick={() => onNavigateToTrack()}
              >
                <Search size={14} color="var(--civic-cyan)" />
                <span>Open Track Docket</span>
                <ArrowRight size={13} style={{ marginLeft: 'auto' }} />
              </button>

              <button
                type="button"
                className="btn-quick-nav"
                onClick={() => onNavigateToEvidence()}
              >
                <Paperclip size={14} color="var(--civic-amber)" />
                <span>Evidence Attachment Studio</span>
                <ArrowRight size={13} style={{ marginLeft: 'auto' }} />
              </button>

              {(isSupervisor || isAdmin) && onNavigateToAudit && (
                <button
                  type="button"
                  className="btn-quick-nav"
                  onClick={() => onNavigateToAudit()}
                >
                  <ShieldCheck size={14} color="var(--civic-emerald)" />
                  <span>Inspect Cedar Audit Trail</span>
                  <ArrowRight size={13} style={{ marginLeft: 'auto' }} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Disclaimers */}
      <div className="authority-disclaimer-box" role="note">
        <ShieldAlert size={14} />
        <span>
          PROTOTYPE AUTHORITY WORKSPACE • Local simulation identity • Server-side Cedar PEP enforces
          departmental boundaries and rejects unauthorized lifecycle shifts. Not an official government
          system.
        </span>
      </div>
    </div>
  );
};
