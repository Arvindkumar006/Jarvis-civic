import React from 'react';
import { ShieldAlert, Sparkles } from 'lucide-react';
import './Navbar.css';

export type ActiveTab = 'experience' | 'report' | 'track' | 'evidence';

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

        {/* Primary Navigation: 01 REPORT, 02 TRACK, 03 EVIDENCE */}
        <nav className="navbar-nav-group" aria-label="Command Center Navigation">
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
        </nav>

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
