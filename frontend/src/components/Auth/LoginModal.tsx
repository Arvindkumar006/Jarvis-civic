import React, { useState, useEffect, useRef } from 'react';
import {
  Lock,
  User,
  Building2,
  Shield,
  Sliders,
  Eye,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  X,
  Sparkles,
  KeyRound,
  ShieldAlert,
} from 'lucide-react';
import { ApplicationRole, LoginCredentials } from '../../types/civic';
import { useAuth } from '../../context/AuthContext';
import './LoginModal.css';

interface QuickAccountChip {
  label: string;
  role: ApplicationRole;
  email: string;
  badge: string;
  dept?: string;
}

const DEV_ACCOUNTS: QuickAccountChip[] = [
  {
    label: 'Citizen User',
    role: ApplicationRole.CITIZEN,
    email: 'citizen@jarviscivic.local',
    badge: 'CITIZEN',
  },
  {
    label: 'PWD Officer',
    role: ApplicationRole.AUTHORITY_OFFICER,
    email: 'pwd.officer@jarviscivic.local',
    badge: 'AUTHORITY',
    dept: 'PWD_ROADS',
  },
  {
    label: 'Roads Officer',
    role: ApplicationRole.AUTHORITY_OFFICER,
    email: 'roads.officer@jarviscivic.local',
    badge: 'AUTHORITY',
    dept: 'PWD_ROADS',
  },
  {
    label: 'Drainage Officer',
    role: ApplicationRole.AUTHORITY_OFFICER,
    email: 'officer@jarviscivic.local',
    badge: 'AUTHORITY',
    dept: 'DRAINAGE_STORMWATER',
  },
  {
    label: 'Stormwater Officer',
    role: ApplicationRole.AUTHORITY_OFFICER,
    email: 'stormwater.officer@jarviscivic.local',
    badge: 'AUTHORITY',
    dept: 'DRAINAGE_STORMWATER',
  },
  {
    label: 'Municipal Supervisor',
    role: ApplicationRole.MUNICIPAL_SUPERVISOR,
    email: 'supervisor@jarviscivic.local',
    badge: 'SUPERVISOR',
    dept: 'DRAINAGE_STORMWATER',
  },
  {
    label: 'System Admin',
    role: ApplicationRole.ADMINISTRATOR,
    email: 'admin@jarviscivic.local',
    badge: 'ADMIN',
  },
  {
    label: 'Public Account',
    role: ApplicationRole.PUBLIC,
    email: 'public@jarviscivic.local',
    badge: 'PUBLIC',
  },
];

const DEV_DEFAULT_PASSWORD = 'JarvisCivic2026!';

export interface LoginModalProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose }) => {
  let auth: ReturnType<typeof useAuth> | null = null;
  try {
    auth = useAuth();
  } catch {
    auth = null;
  }

  const isLoginOpen = isOpen !== undefined ? isOpen : auth?.isLoginOpen ?? false;
  const closeLogin = onClose || auth?.closeLogin || (() => {});
  const login = auth?.login || (async () => {});
  const intendedRole = auth?.intendedRole || null;
  const sessionExpiredMessage = auth?.sessionExpiredMessage || null;
  const clearSessionExpiredMessage = auth?.clearSessionExpiredMessage || (() => {});

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const emailInputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  // Sync sessionExpiredMessage to local error if present
  useEffect(() => {
    if (sessionExpiredMessage) {
      setErrorMessage(sessionExpiredMessage);
    }
  }, [sessionExpiredMessage]);

  // Focus on open
  useEffect(() => {
    if (isLoginOpen) {
      setErrorMessage(sessionExpiredMessage || null);
      // Pre-fill email suggestion if intendedRole is set
      if (intendedRole && !email) {
        const matching = DEV_ACCOUNTS.find((a) => a.role === intendedRole);
        if (matching) {
          setEmail(matching.email);
        }
      }
      const timer = setTimeout(() => {
        if (emailInputRef.current) {
          emailInputRef.current.focus();
        }
      }, 80);
      return () => clearTimeout(timer);
    } else {
      // Clear sensitive form state immediately upon modal close
      setPassword('');
      setErrorMessage(null);
      clearSessionExpiredMessage();
    }
  }, [isLoginOpen, intendedRole]);

  // Keyboard accessibility: Escape to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isLoginOpen) {
        closeLogin();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isLoginOpen, closeLogin]);

  if (!isLoginOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) {
      setErrorMessage('Please enter both email and password.');
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    try {
      await login({
        email: email.trim(),
        password,
      });
      // On success, state is cleaned up and modal is closed inside AuthContext
      setPassword('');
    } catch (err: any) {
      setErrorMessage(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickFill = (acct: QuickAccountChip) => {
    setEmail(acct.email);
    setPassword(DEV_DEFAULT_PASSWORD);
    setErrorMessage(null);
  };

  return (
    <div
      className="login-modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) closeLogin();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Civic Authentication Dialog"
      aria-labelledby="login-modal-title"
    >
      <div className="login-modal-panel crosshair-corner" ref={modalRef}>
        {/* Header Bar */}
        <div className="login-modal-header">
          <div className="login-header-branding">
            <div className="brand-dot-pulse" />
            <div>
              <div className="login-system-tag">
                <span className="technical-label">JARVIS CIVIC // ACCESS CONTROL PLANE</span>
              </div>
              <h2 id="login-modal-title" className="login-modal-headline">
                Civic Authentication
              </h2>
            </div>
          </div>
          <button
            type="button"
            className="login-close-btn"
            onClick={closeLogin}
            aria-label="Cancel"
          >
            <X size={18} />
          </button>
        </div>

        {/* Intended Role Context Badge */}
        {intendedRole && (
          <div className="intended-role-banner">
            <span className="intended-label">WORKSPACE ROLE:</span>
            <strong className="intended-role-badge">
              {intendedRole.replace(/_/g, ' ')}
            </strong>
            <span className="intended-note">
              (Actual workspace derived server-side from account role upon authentication)
            </span>
          </div>
        )}

        {/* Error / Session Expired Notification */}
        {errorMessage && (
          <div className="login-error-banner" role="alert" aria-live="assertive">
            <AlertCircle size={16} className="error-icon" />
            <span className="error-text">{errorMessage}</span>
          </div>
        )}

        {/* Authentication Form */}
        <form onSubmit={handleSubmit} className="login-form" noValidate>
          <div className="login-field-group">
            <label htmlFor="login-email" className="login-field-label">
              <span className="technical-label">ACCOUNT IDENTIFIER // CIVIC USERNAME OR EMAIL</span>
            </label>
            <div className="login-input-wrapper">
              <input
                ref={emailInputRef}
                id="login-email"
                type="email"
                className="login-text-input"
                aria-label="Civic Username"
                placeholder="e.g., citizen@jarviscivic.local"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                disabled={loading}
              />
            </div>
          </div>

          <div className="login-field-group">
            <label htmlFor="login-password" className="login-field-label">
              <span className="technical-label">SECURITY CREDENTIAL // PASSWORD</span>
            </label>
            <div className="login-input-wrapper">
              <input
                id="login-password"
                type="password"
                className="login-text-input"
                aria-label="Account Password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                disabled={loading}
              />
            </div>
          </div>

          {/* Submit Action */}
          <button
            type="submit"
            className="btn-authenticate-submit"
            disabled={loading}
            aria-busy={loading}
            aria-label="Authenticate & Enter Workspace"
          >
            {loading ? (
              <span className="login-loading-inline">
                <span className="btn-spinner" />
                <span>AUTHENTICATING WITH SERVER...</span>
              </span>
            ) : (
              <>
                <KeyRound size={16} />
                <span>SIGN IN & ENTER WORKSPACE</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        {/* Development Helper Chips */}
        <div className="login-dev-accounts-section">
          <div className="dev-accounts-header">
            <span className="technical-label">ALLOCATED DEVELOPMENT ACCOUNTS</span>
            <span className="dev-accounts-sub">Click to populate credentials</span>
          </div>

          <div className="dev-accounts-grid">
            {DEV_ACCOUNTS.map((acct) => (
              <button
                key={acct.email}
                type="button"
                className={`dev-account-chip ${
                  intendedRole === acct.role ? 'chip-recommended' : ''
                }`}
                onClick={() => handleQuickFill(acct)}
                aria-label={`Quick-fill ${acct.role.toLowerCase()}`}
              >
                <div className="chip-top">
                  <span className="chip-badge">{acct.badge}</span>
                  {acct.dept && (
                    <span className="chip-dept">[{acct.dept.replace(/_/g, ' ')}]</span>
                  )}
                </div>
                <div className="chip-name">{acct.label}</div>
                <div className="chip-email">{acct.email}</div>
              </button>
            ))}
          </div>
          <div className="dev-password-note">
            <ShieldAlert size={12} />
            <span>Default local password: <code>{DEV_DEFAULT_PASSWORD}</code> • Verified by server-side Argon2id.</span>
          </div>
        </div>
      </div>
    </div>
  );
};
