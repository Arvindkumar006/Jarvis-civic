import React from 'react';
import { ShieldAlert, LogOut, KeyRound, Lock, User } from 'lucide-react';
import { ApplicationRole } from '../../types/civic';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useAuth } from '../../context/AuthContext';
import './Navbar.css';

export type ActiveTab = 'experience' | 'report' | 'track' | 'evidence' | 'console' | 'audit';

interface NavbarProps {
  activeTab: ActiveTab;
  onSelectTab: (tab: ActiveTab) => void;
  backendOnline: boolean | null;
  docketCount: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onSelectTab,
  backendOnline,
  docketCount,
}) => {
  const { session } = useWorkspace();

  let auth: ReturnType<typeof useAuth> | null = null;
  try {
    auth = useAuth();
  } catch {
    auth = null;
  }

  const isAuthenticated = auth ? auth.isAuthenticated : session.role !== ApplicationRole.PUBLIC;
  const role = auth && auth.isAuthenticated ? auth.role : session.role;
  const department = auth && auth.isAuthenticated ? auth.department : session.department;
  const displayName = auth?.displayName || (session.principalId ? session.label : 'Anonymous');
  const principalId = auth?.principalId || session.principalId;

  const handleLogout = async () => {
    if (auth) {
      await auth.logout();
    }
    onSelectTab('experience');
  };

  const handleOpenLogin = () => {
    if (auth) {
      auth.openLogin();
    }
  };

  return (
    <header className="civic-navbar" role="banner">
      <div className="navbar-inner">
        {/* Brand identity (clicking opens Page 01 Product Experience) */}
        <div className="navbar-brand-section">
          <button
            type="button"
            className="brand-lockup-btn"
            onClick={() => onSelectTab('experience')}
            title="Explore JARVIS Civic Product Experience"
            aria-label="JARVIS Civic Home Experience"
          >
            <div className="brand-lockup">
              <div className="brand-marker">
                <span className="brand-dot" />
              </div>
              <div className="brand-meta">
                <div className="brand-title-wrap">
                  <span className="brand-title">JARVIS</span>
                  <span className="brand-title-bold">CIVIC</span>
                  <span className="brand-version">SYSTEM // v1.0</span>
                </div>
                <span className="brand-tagline">Speak. Report. Resolve.</span>
              </div>
            </div>
          </button>

          <div className="navbar-prototype-flag" role="note">
            <ShieldAlert size={12} />
            <span>PROTOTYPE • NOT A GOVERNMENT PORTAL</span>
          </div>
        </div>

        {/* Dynamic Role-Aware Navigation */}
        <nav className="navbar-nav-group" aria-label="Command Center Navigation">
          {/* UNAUTHENTICATED NAVIGATION */}
          {!isAuthenticated && (
            <>
              <button
                type="button"
                className={`nav-btn ${activeTab === 'experience' ? 'active' : ''}`}
                onClick={() => onSelectTab('experience')}
                aria-current={activeTab === 'experience' ? 'page' : undefined}
              >
                <span className="nav-index">01</span>
                <span className="nav-title">Home / Experience</span>
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'track' ? 'active' : ''}`}
                onClick={() => onSelectTab('track')}
                aria-current={activeTab === 'track' ? 'page' : undefined}
              >
                <span className="nav-index">02</span>
                <span className="nav-title">Public Tracking</span>
                {docketCount > 0 && <span className="nav-count-badge">{docketCount}</span>}
              </button>
            </>
          )}

          {/* CITIZEN WORKSPACE: 01 Report, 02 Track, 03 Evidence */}
          {isAuthenticated && role === ApplicationRole.CITIZEN && (
            <>
              <button
                type="button"
                className={`nav-btn ${activeTab === 'report' ? 'active' : ''}`}
                onClick={() => onSelectTab('report')}
                aria-current={activeTab === 'report' ? 'page' : undefined}
              >
                <span className="nav-index">01</span>
                <span className="nav-title">Report Issue</span>
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'track' ? 'active' : ''}`}
                onClick={() => onSelectTab('track')}
                aria-current={activeTab === 'track' ? 'page' : undefined}
              >
                <span className="nav-index">02</span>
                <span className="nav-title">Track Docket</span>
                {docketCount > 0 && <span className="nav-count-badge">{docketCount}</span>}
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'evidence' ? 'active' : ''}`}
                onClick={() => onSelectTab('evidence')}
                aria-current={activeTab === 'evidence' ? 'page' : undefined}
              >
                <span className="nav-index">03</span>
                <span className="nav-title">Evidence Studio</span>
              </button>
            </>
          )}

          {/* AUTHENTICATED PUBLIC: 01 Public Tracking */}
          {isAuthenticated && role === ApplicationRole.PUBLIC && (
            <button
              type="button"
              className={`nav-btn ${activeTab === 'track' ? 'active' : ''}`}
              onClick={() => onSelectTab('track')}
              aria-current={activeTab === 'track' ? 'page' : undefined}
            >
              <span className="nav-index">01</span>
              <span className="nav-title">Public Tracking</span>
            </button>
          )}

          {/* AUTHORITY OFFICER WORKSPACE: 01 Authority Console, 02 Track Docket, 03 Evidence */}
          {isAuthenticated && role === ApplicationRole.AUTHORITY_OFFICER && (
            <>
              <button
                type="button"
                className={`nav-btn ${activeTab === 'console' ? 'active' : ''}`}
                onClick={() => onSelectTab('console')}
                aria-current={activeTab === 'console' ? 'page' : undefined}
              >
                <span className="nav-index">01</span>
                <span className="nav-title">Authority Console</span>
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'track' ? 'active' : ''}`}
                onClick={() => onSelectTab('track')}
                aria-current={activeTab === 'track' ? 'page' : undefined}
              >
                <span className="nav-index">02</span>
                <span className="nav-title">Track Docket</span>
                {docketCount > 0 && <span className="nav-count-badge">{docketCount}</span>}
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'evidence' ? 'active' : ''}`}
                onClick={() => onSelectTab('evidence')}
                aria-current={activeTab === 'evidence' ? 'page' : undefined}
              >
                <span className="nav-index">03</span>
                <span className="nav-title">Evidence</span>
              </button>
            </>
          )}

          {/* MUNICIPAL SUPERVISOR WORKSPACE: 01 Supervisor Console, 02 Track, 03 Evidence, 04 Audit */}
          {isAuthenticated && role === ApplicationRole.MUNICIPAL_SUPERVISOR && (
            <>
              <button
                type="button"
                className={`nav-btn ${activeTab === 'console' ? 'active' : ''}`}
                onClick={() => onSelectTab('console')}
                aria-current={activeTab === 'console' ? 'page' : undefined}
              >
                <span className="nav-index">01</span>
                <span className="nav-title">Supervisor Console</span>
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'track' ? 'active' : ''}`}
                onClick={() => onSelectTab('track')}
                aria-current={activeTab === 'track' ? 'page' : undefined}
              >
                <span className="nav-index">02</span>
                <span className="nav-title">Track Docket</span>
                {docketCount > 0 && <span className="nav-count-badge">{docketCount}</span>}
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'evidence' ? 'active' : ''}`}
                onClick={() => onSelectTab('evidence')}
                aria-current={activeTab === 'evidence' ? 'page' : undefined}
              >
                <span className="nav-index">03</span>
                <span className="nav-title">Evidence</span>
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'audit' ? 'active' : ''}`}
                onClick={() => onSelectTab('audit')}
                aria-current={activeTab === 'audit' ? 'page' : undefined}
              >
                <span className="nav-index">04</span>
                <span className="nav-title">Audit Trail</span>
              </button>
            </>
          )}

          {/* ADMINISTRATOR WORKSPACE: 01 Admin Console, 02 Track, 03 Evidence, 04 Audit */}
          {isAuthenticated && role === ApplicationRole.ADMINISTRATOR && (
            <>
              <button
                type="button"
                className={`nav-btn ${activeTab === 'console' ? 'active' : ''}`}
                onClick={() => onSelectTab('console')}
                aria-current={activeTab === 'console' ? 'page' : undefined}
              >
                <span className="nav-index">01</span>
                <span className="nav-title">Admin Console</span>
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'track' ? 'active' : ''}`}
                onClick={() => onSelectTab('track')}
                aria-current={activeTab === 'track' ? 'page' : undefined}
              >
                <span className="nav-index">02</span>
                <span className="nav-title">Track Docket</span>
                {docketCount > 0 && <span className="nav-count-badge">{docketCount}</span>}
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'evidence' ? 'active' : ''}`}
                onClick={() => onSelectTab('evidence')}
                aria-current={activeTab === 'evidence' ? 'page' : undefined}
              >
                <span className="nav-index">03</span>
                <span className="nav-title">Evidence</span>
              </button>

              <button
                type="button"
                className={`nav-btn ${activeTab === 'audit' ? 'active' : ''}`}
                onClick={() => onSelectTab('audit')}
                aria-current={activeTab === 'audit' ? 'page' : undefined}
              >
                <span className="nav-index">04</span>
                <span className="nav-title">Audit Trail</span>
              </button>
            </>
          )}
        </nav>

        {/* Global Identity Display & Auth Action Section */}
        <div className="navbar-workspace-section">
          {isAuthenticated ? (
            <>
              <div
                className="workspace-indicator-pill"
                data-testid="navbar-identity-pill"
                title={`Authenticated principal: ${principalId}`}
              >
                <div className="pill-user-name">
                  <User size={11} className="pill-icon" />
                  <span>{displayName}</span>
                </div>
                <div className="pill-role-label">
                  {role === ApplicationRole.CITIZEN
                    ? 'CITIZEN WORKSPACE'
                    : role === ApplicationRole.PUBLIC
                    ? 'PUBLIC TRACKING'
                    : role === ApplicationRole.AUTHORITY_OFFICER
                    ? 'AUTHORITY WORKSPACE'
                    : role === ApplicationRole.MUNICIPAL_SUPERVISOR
                    ? 'SUPERVISOR WORKSPACE'
                    : 'ADMINISTRATOR'}
                </div>
                {department && (
                  <div className="pill-dept-label">[{department.replace(/_/g, ' ')}]</div>
                )}
                <div className="pill-sec-status">
                  <span className="sec-dot" />
                  <span className="pid-code">({principalId})</span>
                </div>
              </div>

              <button
                type="button"
                className="btn-logout-nav"
                onClick={handleLogout}
                title="Invalidate session and sign out"
                aria-label="Logout session"
              >
                <LogOut size={13} />
                <span>LOGOUT</span>
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn-signin-nav"
              onClick={handleOpenLogin}
              title="Authenticate with allocated civic account"
              aria-label="Sign In"
            >
              <KeyRound size={13} />
              <span>SIGN IN</span>
            </button>
          )}
        </div>

        {/* System Telemetry Indicator */}
        <div className="navbar-telemetry" aria-live="polite">
          <div
            className={`telemetry-light ${
              backendOnline === true ? 'live' : backendOnline === false ? 'down' : 'sync'
            }`}
          />
          <span className="telemetry-label">
            {backendOnline === true ? 'ENGINE ONLINE' : backendOnline === false ? 'ENGINE OFFLINE' : 'INITIALIZING'}
          </span>
        </div>
      </div>
    </header>
  );
};
