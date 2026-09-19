import React, { useState } from 'react';
import {
  User,
  Shield,
  Building2,
  Lock,
  Eye,
  ArrowRight,
  ShieldAlert,
  Sliders,
  CheckCircle2,
  X,
} from 'lucide-react';
import { ApplicationRole, ControlledDepartment } from '../../types/civic';
import { useWorkspace, WORKSPACE_METADATA, DEFAULT_PRINCIPALS } from '../../context/WorkspaceContext';
import './WorkspaceSelector.css';

interface WorkspaceSelectorProps {
  onWorkspaceSelected?: () => void;
  allowCancel?: boolean;
}

const ROLES_ORDER: {
  role: ApplicationRole;
  index: string;
  icon: React.ReactNode;
  badge: string;
  badgeColor: string;
}[] = [
  {
    role: ApplicationRole.CITIZEN,
    index: '01',
    icon: <User size={22} color="var(--civic-cyan)" />,
    badge: 'CITIZEN ACCESS',
    badgeColor: 'var(--civic-cyan)',
  },
  {
    role: ApplicationRole.AUTHORITY_OFFICER,
    index: '02',
    icon: <Building2 size={22} color="var(--civic-amber)" />,
    badge: 'DEPARTMENTAL AUTHORITY',
    badgeColor: 'var(--civic-amber)',
  },
  {
    role: ApplicationRole.MUNICIPAL_SUPERVISOR,
    index: '03',
    icon: <Shield size={22} color="var(--civic-emerald)" />,
    badge: 'SUPERVISORY OVERSIGHT',
    badgeColor: 'var(--civic-emerald)',
  },
  {
    role: ApplicationRole.ADMINISTRATOR,
    index: '04',
    icon: <Sliders size={22} color="#a78bfa" />,
    badge: 'CONTROL PLANE',
    badgeColor: '#a78bfa',
  },
  {
    role: ApplicationRole.PUBLIC,
    index: '05',
    icon: <Eye size={22} color="var(--text-muted)" />,
    badge: 'ANONYMOUS QUERY',
    badgeColor: 'var(--text-muted)',
  },
];

const DEPARTMENTS = [
  { code: ControlledDepartment.DRAINAGE_STORMWATER, name: 'Drainage & Stormwater' },
  { code: ControlledDepartment.PWD_ROADS, name: 'PWD / Roads & Bridges' },
  { code: ControlledDepartment.MUNICIPAL_CORPORATION, name: 'Municipal Corporation General' },
  { code: ControlledDepartment.WASTE_MANAGEMENT, name: 'Solid Waste Management' },
  { code: ControlledDepartment.WATER_SUPPLY, name: 'Metro Water Supply & Sewerage' },
  { code: ControlledDepartment.ELECTRICITY_UTILITY, name: 'Electricity Utility & Lighting' },
  { code: ControlledDepartment.OTHER_MANUAL_REVIEW, name: 'Other / Manual Triage' },
];

export const WorkspaceSelector: React.FC<WorkspaceSelectorProps> = ({
  onWorkspaceSelected,
  allowCancel = false,
}) => {
  const { session, selectWorkspace, cancelWorkspaceSwitch } = useWorkspace();

  // Pending selected role
  const [selectedRole, setSelectedRole] = useState<ApplicationRole>(session.role);
  // Authority configuration step (departments & principal id)
  const [isConfiguringAuthority, setIsConfiguringAuthority] = useState<boolean>(false);
  const [configuredDept, setConfiguredDept] = useState<ControlledDepartment>(
    session.department || ControlledDepartment.DRAINAGE_STORMWATER
  );
  const [configuredPrincipalId, setConfiguredPrincipalId] = useState<string>(
    session.principalId || DEFAULT_PRINCIPALS[ApplicationRole.AUTHORITY_OFFICER]
  );

  const handleSelectRole = (role: ApplicationRole) => {
    setSelectedRole(role);
    if (
      role === ApplicationRole.AUTHORITY_OFFICER ||
      role === ApplicationRole.MUNICIPAL_SUPERVISOR
    ) {
      setConfiguredPrincipalId(DEFAULT_PRINCIPALS[role]);
      setIsConfiguringAuthority(true);
    } else {
      // Immediate selection for Citizen, Administrator, Public
      selectWorkspace(role);
      if (onWorkspaceSelected) onWorkspaceSelected();
    }
  };

  const handleConfirmAuthorityWorkspace = (e: React.FormEvent) => {
    e.preventDefault();
    selectWorkspace(selectedRole, configuredDept, configuredPrincipalId);
    setIsConfiguringAuthority(false);
    if (onWorkspaceSelected) onWorkspaceSelected();
  };

  return (
    <section
      className="workspace-selector-experience crosshair-corner animate-fade-in"
      aria-label="Workspace Selection"
    >
      {/* Background Ambience */}
      <div className="selector-atmosphere-grid" aria-hidden="true" />

      {/* Top Header */}
      <div className="workspace-selector-header">
        <div className="selector-brand-kicker">
          <span className="selector-dot" />
          <span className="technical-label">JARVIS CIVIC // WORKSPACE ORCHESTRATION</span>
          {allowCancel && (
            <button
              type="button"
              className="btn-cancel-selector"
              onClick={cancelWorkspaceSwitch}
              aria-label="Close workspace selector"
            >
              <X size={15} />
              <span>RETURN TO WORKSPACE</span>
            </button>
          )}
        </div>

        <h2 className="selector-main-title">WHO IS ACCESSING JARVIS CIVIC?</h2>
        <p className="selector-sub-title">
          Select a workspace to configure the civic intelligence experience. The application shell,
          navigation, workflows, and Cedar security policies adapt to your operational context.
        </p>

        <div className="selector-prototype-banner" role="note">
          <ShieldAlert size={14} />
          <span>
            PROTOTYPE WORKSPACE SELECTION • Frontend simulation identity • Server-side Cedar PEP
            remains authoritative.
          </span>
        </div>
      </div>

      {/* MAIN CONTENT: Role Cards Grid OR Authority Config Step */}
      {!isConfiguringAuthority ? (
        <div
          className="workspace-cards-grid"
          role="radiogroup"
          aria-label="Available Civic Workspaces"
        >
          {ROLES_ORDER.map((item) => {
            const meta = WORKSPACE_METADATA[item.role];
            const isActive = session.role === item.role;

            return (
              <div
                key={item.role}
                className={`workspace-card ${isActive ? 'current-active' : ''}`}
                tabIndex={0}
                role="radio"
                aria-checked={isActive}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleSelectRole(item.role);
                  }
                }}
              >
                <div className="card-top-row">
                  <span className="card-index-tag">{item.index}</span>
                  <div className="card-badge" style={{ borderColor: item.badgeColor, color: item.badgeColor }}>
                    {item.badge}
                  </div>
                  {isActive && (
                    <span className="active-pill">
                      <CheckCircle2 size={12} color="var(--civic-emerald)" />
                      <span>ACTIVE WORKSPACE</span>
                    </span>
                  )}
                </div>

                <div className="card-icon-title">
                  <div className="card-icon-box">{item.icon}</div>
                  <h3 className="card-title">{meta.label}</h3>
                </div>

                <p className="card-description">{meta.description}</p>

                <div className="card-capabilities">
                  <span className="technical-label">CAPABILITIES:</span>
                  <ul className="capabilities-list">
                    {meta.capabilities.map((cap, i) => (
                      <li key={i} className="capability-item">
                        <span className="cap-bullet">›</span>
                        <span>{cap}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="card-footer-action">
                  <button
                    type="button"
                    className="btn-enter-workspace"
                    onClick={() => handleSelectRole(item.role)}
                    aria-label={`Enter ${meta.label}`}
                  >
                    <span>ENTER WORKSPACE</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* STEP 2: AUTHORITY WORKSPACE CONFIGURATION */
        <div className="authority-config-modal animate-fade-in" role="region" aria-label="Authority Configuration">
          <div className="authority-config-card crosshair-corner">
            <div className="config-header">
              <div className="config-title-group">
                <Building2 size={20} color="var(--civic-amber)" />
                <div>
                  <span className="technical-label">
                    {selectedRole === ApplicationRole.AUTHORITY_OFFICER
                      ? 'AUTHORITY OFFICER WORKSPACE'
                      : 'MUNICIPAL SUPERVISOR WORKSPACE'}
                  </span>
                  <h3 className="config-title">Configure Authority Department & Identity</h3>
                </div>
              </div>

              <button
                type="button"
                className="btn-back-roles"
                onClick={() => setIsConfiguringAuthority(false)}
                aria-label="Back to role selection"
              >
                ‹ BACK TO ROLES
              </button>
            </div>

            <p className="config-explanation">
              Authority workspaces operate under strict fail-closed departmental scoping. Select the
              department jurisdiction and simulation identity for this session.
            </p>

            <form onSubmit={handleConfirmAuthorityWorkspace} className="authority-config-form">
              <div className="config-form-group">
                <label htmlFor="auth-dept-select" className="technical-label">
                  ASSIGNED DEPARTMENT JURISDICTION:
                </label>
                <select
                  id="auth-dept-select"
                  className="config-select-field"
                  value={configuredDept}
                  onChange={(e) => setConfiguredDept(e.target.value as ControlledDepartment)}
                >
                  {DEPARTMENTS.map((d) => (
                    <option key={d.code} value={d.code}>
                      {d.code} — {d.name}
                    </option>
                  ))}
                </select>
                <span className="field-hint">
                  Cedar authorization validates that status transitions match this assigned department.
                </span>
              </div>

              <div className="config-form-group">
                <label htmlFor="auth-principal-input" className="technical-label">
                  LOCAL SIMULATION IDENTITY (PRINCIPAL ID):
                </label>
                <input
                  id="auth-principal-input"
                  type="text"
                  className="config-input-field"
                  value={configuredPrincipalId}
                  onChange={(e) => setConfiguredPrincipalId(e.target.value)}
                  placeholder="e.g. authority-officer-local-01"
                />
                <span className="field-hint">
                  Local simulation identity. Sent via <code>X-Principal-Id</code> header to Cedar PEP.
                </span>
              </div>

              <div className="config-disclosure-box">
                <Lock size={14} color="var(--civic-emerald)" />
                <span>
                  Prototype workspace. Server-side Cedar policies remain authoritative. Frontend
                  identity configuration cannot override backend Cedar authorization rules.
                </span>
              </div>

              <div className="config-actions-row">
                <button
                  type="button"
                  className="btn-dialog-cancel"
                  onClick={() => setIsConfiguringAuthority(false)}
                >
                  CANCEL
                </button>
                <button type="submit" className="btn-enter-authority-console">
                  <span>ENTER AUTHORITY CONSOLE</span>
                  <ArrowRight size={15} />
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
};
