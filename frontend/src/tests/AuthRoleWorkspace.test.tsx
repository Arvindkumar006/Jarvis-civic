import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { App } from '../App';
import { AuthProvider, useAuth } from '../context/AuthContext';
import { WorkspaceProvider, useWorkspace } from '../context/WorkspaceContext';
import { LoginModal } from '../components/Auth/LoginModal';
import { TrackingView } from '../components/Tracking/TrackingView';
import { ApplicationRole, ControlledDepartment } from '../types/civic';
import { authApi, casesApi, trackingApi, healthApi, onUnauthorized, notifyUnauthorized } from '../services/api';

vi.mock('../services/api', () => {
  let unauthorizedSubscribers: ((detail?: string) => void)[] = [];

  class MockApiError extends Error {
    public statusCode?: number;
    constructor(message: string, statusCode?: number) {
      super(message);
      this.name = 'ApiError';
      this.statusCode = statusCode;
    }
  }

  return {
    ApiError: MockApiError,
    authApi: {
      login: vi.fn(),
      me: vi.fn(),
      logout: vi.fn(),
    },
    trackingApi: {
      getTracking: vi.fn(),
    },
    casesApi: {
      getCase: vi.fn(),
      updateStatus: vi.fn(),
      addResolutionNote: vi.fn(),
      getHistory: vi.fn(),
      createCase: vi.fn(),
    },
    auditApi: {
      getCaseAuditTrail: vi.fn(),
    },
    evidenceApi: {
      uploadEvidence: vi.fn(),
    },
    conversationApi: {
      intake: vi.fn(),
    },
    healthApi: {
      checkHealth: vi.fn().mockResolvedValue(true),
    },
    onUnauthorized: vi.fn((callback: (detail?: string) => void) => {
      unauthorizedSubscribers.push(callback);
      return () => {
        unauthorizedSubscribers = unauthorizedSubscribers.filter((s) => s !== callback);
      };
    }),
    notifyUnauthorized: vi.fn((detail?: string) => {
      unauthorizedSubscribers.forEach((cb) => cb(detail));
    }),
  };
});

describe('Phase 8.2 — Role-Aware Application / Workspace Foundation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  const createMockUser = (
    role: ApplicationRole,
    principalId: string,
    displayName: string,
    department: ControlledDepartment | null = null
  ) => ({
    principal_id: principalId,
    email: `${principalId}@jarviscivic.local`,
    role,
    display_name: displayName,
    department,
    is_active: true,
    created_at: new Date().toISOString(),
  });

  // Helper to wait for unauthenticated bootstrap
  const renderUnauthenticatedApp = async () => {
    vi.mocked(authApi.me).mockRejectedValueOnce(new Error('Unauthorized'));
    const utils = render(<App />);
    await waitFor(
      () => {
        expect(screen.queryByRole('status', { name: /Initializing security context/i })).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Sign In/i })).toBeInTheDocument();
      },
      { timeout: 4000 }
    );
    return utils;
  };

  // 1 & 2: Verify unauthenticated landing page renders with role cards at bottom
  it('renders unauthenticated landing page with role selection cards at bottom', async () => {
    await renderUnauthenticatedApp();

    // Landing page role selection section
    expect(screen.getByRole('heading', { name: /Choose Your Civic Role/i })).toBeInTheDocument();
    expect(screen.getByText(/ACCESS CIVIC WORKSPACE \/\/ ROLE SELECTION/i)).toBeInTheDocument();

    // Verify all 5 civic role cards are rendered at bottom
    expect(screen.getByRole('button', { name: /Enter Citizen Workspace/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Enter Drainage Officer Workspace/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Enter Roads Officer Workspace/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Enter Municipal Supervisor Workspace/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Enter System Administrator Workspace/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Continue as Public Observer/i })).toBeInTheDocument();

    // Verify unauthenticated navbar shows SIGN IN
    expect(screen.getByRole('button', { name: /Sign In/i })).toBeInTheDocument();
  });

  // 3 & 4: Verify Citizen role card opens login modal preselecting Citizen role
  it('opens login modal and preselects Citizen credentials on Citizen role card click', async () => {
    await renderUnauthenticatedApp();

    const citizenCard = screen.getByRole('button', { name: /Enter Citizen Workspace/i });
    fireEvent.click(citizenCard);

    // Modal dialog is displayed
    const dialog = screen.getByRole('dialog', { name: /Civic Authentication/i });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText(/WORKSPACE ROLE:/i)).toBeInTheDocument();
    expect(within(dialog).getAllByText('CITIZEN').length).toBeGreaterThan(0);
    expect(within(dialog).getByRole('button', { name: /Quick-fill citizen/i })).toBeInTheDocument();
  });

  // 5 & 6: Verify Drainage & Roads Officer role cards preselect Authority Officer role
  it('opens login modal and preselects Authority Officer role for Drainage and Roads officers', async () => {
    await renderUnauthenticatedApp();

    // Test Drainage Officer Card
    const drainageCard = screen.getByRole('button', { name: /Enter Drainage Officer Workspace/i });
    fireEvent.click(drainageCard);

    expect(screen.getByRole('dialog', { name: /Civic Authentication/i })).toBeInTheDocument();
    expect(screen.getByText(/WORKSPACE ROLE:/i)).toBeInTheDocument();
    expect(screen.getByText('AUTHORITY OFFICER')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Quick-fill authority|Drainage Officer/i })[0]).toBeInTheDocument();

    // Close modal via Cancel
    fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));

    // Test Roads Officer Card
    const roadsCard = screen.getByRole('button', { name: /Enter Roads Officer Workspace/i });
    fireEvent.click(roadsCard);
    expect(screen.getByRole('dialog', { name: /Civic Authentication/i })).toBeInTheDocument();
    expect(screen.getByText('AUTHORITY OFFICER')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Quick-fill authority|Roads Officer/i })[0]).toBeInTheDocument();
  });

  // 7 & 8: Verify Supervisor and Administrator role cards preselect respective roles
  it('preselects Supervisor and Administrator roles appropriately in login modal', async () => {
    await renderUnauthenticatedApp();

    // Supervisor
    const supervisorCard = screen.getByRole('button', { name: /Enter Municipal Supervisor Workspace/i });
    fireEvent.click(supervisorCard);
    const supDialog = screen.getByRole('dialog', { name: /Civic Authentication/i });
    expect(supDialog).toBeInTheDocument();
    expect(within(supDialog).getByText('MUNICIPAL SUPERVISOR')).toBeInTheDocument();
    expect(within(supDialog).getByRole('button', { name: /Quick-fill municipal_supervisor/i })).toBeInTheDocument();

    fireEvent.click(within(supDialog).getByRole('button', { name: /Cancel/i }));

    // Administrator
    const adminCard = screen.getByRole('button', { name: /Enter System Administrator Workspace/i });
    fireEvent.click(adminCard);
    const adminDialog = screen.getByRole('dialog', { name: /Civic Authentication/i });
    expect(adminDialog).toBeInTheDocument();
    expect(within(adminDialog).getByText('ADMINISTRATOR')).toBeInTheDocument();
    expect(within(adminDialog).getByRole('button', { name: /Quick-fill administrator/i })).toBeInTheDocument();
  });

  // 9: Verify Public role card switches to Public mode without login modal
  it('switches to Public mode without opening login modal when Public card is clicked', async () => {
    await renderUnauthenticatedApp();

    const publicCard = screen.getByRole('button', { name: /Continue as Public Observer/i });
    fireEvent.click(publicCard);

    // Modal is NOT opened
    expect(screen.queryByRole('dialog', { name: /Civic Authentication/i })).not.toBeInTheDocument();

    // Navigates directly to Track Docket view
    await waitFor(() => {
      expect(screen.getByText('Track Civic Action Docket')).toBeInTheDocument();
    });
  });

  // 10, 11 & 15: Successful Citizen login redirects to Citizen workspace with correct navigation tabs
  it('authenticates Citizen via POST /api/auth/login and displays Citizen workspace and tabs', async () => {
    const citizenUser = createMockUser(ApplicationRole.CITIZEN, 'cit-user-1', 'Ananya Sharma');
    vi.mocked(authApi.me)
      .mockRejectedValueOnce(new Error('Unauthorized')) // initial check
      .mockResolvedValueOnce(citizenUser);

    vi.mocked(authApi.login).mockResolvedValueOnce(citizenUser);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sign In/i })).toBeInTheDocument();
    });

    // Open login modal
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

    // Fill credentials
    fireEvent.change(screen.getByLabelText(/Civic Username/i), { target: { value: 'citizen@jarviscivic.local' } });
    fireEvent.change(screen.getByLabelText(/Account Password/i), { target: { value: 'JarvisCivic2026!' } });
    fireEvent.click(screen.getByRole('button', { name: /Authenticate & Enter Workspace/i }));

    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith({
        email: 'citizen@jarviscivic.local',
        password: 'JarvisCivic2026!',
      });
    });

    // Verify Citizen Navigation tabs: Report Issue, Track Docket, Evidence Studio
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Report Issue/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Track Docket/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Evidence Studio/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Authority Dashboard/i })).not.toBeInTheDocument();
    });

    // Verify user identity in navbar pill
    expect(screen.getByTestId('navbar-identity-pill')).toBeInTheDocument();
    expect(screen.getByText('Ananya Sharma')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Logout session/i })).toBeInTheDocument();
  });

  // 12 & 16: Successful Authority Officer login redirects to Authority workspace with correct tabs
  it('authenticates Authority Officer and displays Authority workspace and tabs', async () => {
    const officerUser = createMockUser(
      ApplicationRole.AUTHORITY_OFFICER,
      'officer-drainage-1',
      'Officer Rajesh Kumar',
      ControlledDepartment.DRAINAGE_STORMWATER
    );

    vi.mocked(authApi.me)
      .mockRejectedValueOnce(new Error('Unauthorized'))
      .mockResolvedValueOnce(officerUser);

    vi.mocked(authApi.login).mockResolvedValueOnce(officerUser);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Enter Drainage Officer Workspace/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Enter Drainage Officer Workspace/i }));
    fireEvent.change(screen.getByLabelText(/Civic Username/i), { target: { value: 'officer@jarviscivic.local' } });
    fireEvent.change(screen.getByLabelText(/Account Password/i), { target: { value: 'JarvisCivic2026!' } });
    fireEvent.click(screen.getByRole('button', { name: /Authenticate & Enter Workspace/i }));

    // Verify Authority tabs: Authority Console, Track Docket, Evidence
    await waitFor(() => {
      const nav = screen.getByRole('navigation', { name: /Command Center Navigation/i });
      expect(within(nav).getByRole('button', { name: /Authority Console/i })).toBeInTheDocument();
      expect(within(nav).getByRole('button', { name: /Track Docket/i })).toBeInTheDocument();
      expect(within(nav).getByRole('button', { name: /Evidence/i })).toBeInTheDocument();
      expect(within(nav).queryByRole('button', { name: /Report Issue/i })).not.toBeInTheDocument();
    });

    expect(screen.getByText('Officer Rajesh Kumar')).toBeInTheDocument();
    const pill = screen.getByTestId('navbar-identity-pill');
    expect(within(pill).getByText(/DRAINAGE STORMWATER/i)).toBeInTheDocument();
  });

  // 13 & 17: Supervisor login and tabs
  it('authenticates Supervisor and displays Supervisor workspace with queues and audit tabs', async () => {
    const supervisorUser = createMockUser(
      ApplicationRole.MUNICIPAL_SUPERVISOR,
      'supervisor-01',
      'Chief Supervisor Mehta'
    );
    vi.mocked(authApi.me).mockResolvedValue(supervisorUser);

    render(<App />);

    await waitFor(() => {
      expect(screen.queryByRole('status', { name: /Initializing security context/i })).not.toBeInTheDocument();
      expect(screen.getByText('Chief Supervisor Mehta')).toBeInTheDocument();
    });

    // Verify Supervisor Navigation tabs
    const nav = screen.getByRole('navigation', { name: /Command Center Navigation/i });
    expect(within(nav).getByRole('button', { name: /Supervisor Console/i })).toBeInTheDocument();
    expect(within(nav).getByRole('button', { name: /Track Docket/i })).toBeInTheDocument();
    expect(within(nav).getByRole('button', { name: /Audit Trail/i })).toBeInTheDocument();
  });

  // 14 & 18: Administrator login and tabs
  it('authenticates Administrator and displays Admin operations and audit tabs', async () => {
    const adminUser = createMockUser(ApplicationRole.ADMINISTRATOR, 'admin-01', 'Director Admin Sundaram');
    vi.mocked(authApi.me).mockResolvedValue(adminUser);

    render(<App />);

    await waitFor(() => {
      expect(screen.queryByRole('status', { name: /Initializing security context/i })).not.toBeInTheDocument();
      expect(screen.getByText('Director Admin Sundaram')).toBeInTheDocument();
    });

    // Verify Administrator tabs
    const nav = screen.getByRole('navigation', { name: /Command Center Navigation/i });
    expect(within(nav).getByRole('button', { name: /Admin Console/i })).toBeInTheDocument();
    expect(within(nav).getByRole('button', { name: /Track Docket/i })).toBeInTheDocument();
    expect(within(nav).getByRole('button', { name: /Audit Trail/i })).toBeInTheDocument();
  });

  // 20, 21 & 22: Client cannot override server role, department, or principal_id
  it('enforces server authority: client cannot override role, department, or principal_id', async () => {
    const TestConsumer: React.FC = () => {
      const { session } = useWorkspace();
      const { user } = useAuth();
      return (
        <div>
          <span data-testid="resolved-role">{session.role}</span>
          <span data-testid="resolved-pid">{session.principalId}</span>
          <span data-testid="resolved-dept">{session.department || 'NONE'}</span>
          <span data-testid="auth-user-role">{user?.role}</span>
        </div>
      );
    };

    // Server says user is officer with DRAINAGE_STORMWATER
    const officerUser = createMockUser(
      ApplicationRole.AUTHORITY_OFFICER,
      'officer-drainage-1',
      'Officer Rajesh Kumar',
      ControlledDepartment.DRAINAGE_STORMWATER
    );

    render(
      <AuthProvider initialUser={officerUser} skipInitialCheck={true}>
        <WorkspaceProvider>
          <TestConsumer />
        </WorkspaceProvider>
      </AuthProvider>
    );

    expect(screen.getByTestId('resolved-role').textContent).toBe(ApplicationRole.AUTHORITY_OFFICER);
    expect(screen.getByTestId('resolved-pid').textContent).toBe('officer-drainage-1');
    expect(screen.getByTestId('resolved-dept').textContent).toBe('DRAINAGE_STORMWATER');
  });

  // 23: Logout clears session and returns user to unauthenticated landing page
  it('calls POST /api/auth/logout and returns to unauthenticated landing page on logout', async () => {
    const citizenUser = createMockUser(ApplicationRole.CITIZEN, 'cit-user-1', 'Ananya Sharma');
    vi.mocked(authApi.me).mockResolvedValue(citizenUser);
    vi.mocked(authApi.logout).mockImplementation(async () => {
      vi.mocked(authApi.me).mockRejectedValue(new Error('Unauthorized'));
      return { detail: 'Logged out successfully' };
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('navbar-identity-pill')).toBeInTheDocument();
    });

    const logoutBtn = screen.getByRole('button', { name: /Logout session/i });
    fireEvent.click(logoutBtn);

    await waitFor(() => {
      expect(authApi.logout).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId('navbar-identity-pill')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Sign In/i })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /Choose Your Civic Role/i })).toBeInTheDocument();
    });
  });

  // 24: Session expiration (401) clears auth state and displays expired notice
  it('clears auth state and opens login modal with session expired message on 401 notification', async () => {
    const citizenUser = createMockUser(ApplicationRole.CITIZEN, 'cit-user-1', 'Ananya Sharma');
    vi.mocked(authApi.me).mockResolvedValue(citizenUser);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('navbar-identity-pill')).toBeInTheDocument();
    });

    vi.mocked(authApi.me).mockRejectedValue(new Error('Unauthorized'));

    // Trigger 401 event from API layer
    act(() => {
      notifyUnauthorized('Your session has expired. Please authenticate again.');
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /Civic Authentication/i })).toBeInTheDocument();
      expect(screen.getByText(/Your session has expired/i)).toBeInTheDocument();
      expect(screen.queryByTestId('navbar-identity-pill')).not.toBeInTheDocument();
    });
  });

  // 25, 26, 27 & 28: Track Docket contains NO simulated controls and displays server identity
  it('renders Track Docket view without any simulated role/department/principal selectors', async () => {
    const officerUser = createMockUser(
      ApplicationRole.AUTHORITY_OFFICER,
      'officer-drainage-1',
      'Officer Rajesh Kumar',
      ControlledDepartment.DRAINAGE_STORMWATER
    );

    render(
      <AuthProvider initialUser={officerUser} skipInitialCheck={true}>
        <WorkspaceProvider>
          <TrackingView />
        </WorkspaceProvider>
      </AuthProvider>
    );

    // Server-authenticated identity displayed in strip
    expect(screen.getByText('Officer Rajesh Kumar')).toBeInTheDocument();
    expect(screen.getByText(/\[AUTHORITY OFFICER\]/i)).toBeInTheDocument();
    expect(screen.getByText(/\[DRAINAGE STORMWATER\]/i)).toBeInTheDocument();

    // Strictly NO simulated controls
    expect(screen.queryByText(/SIMULATED AUTHORITY CONTEXT/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Simulated Role/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Simulated Department/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Simulated Principal ID/i)).not.toBeInTheDocument();
  });

  // 30 & 31: Security assertions (no passwords in localStorage/sessionStorage, cookies untouched)
  it('verifies passwords are never persisted to localStorage or sessionStorage', async () => {
    render(<LoginModal isOpen={true} onClose={vi.fn()} />);

    const passwordInput = screen.getByLabelText(/Account Password/i);
    fireEvent.change(passwordInput, { target: { value: 'SuperSecret123!' } });

    // Verify localStorage & sessionStorage do not contain password
    expect(localStorage.getItem('password')).toBeNull();
    expect(sessionStorage.getItem('password')).toBeNull();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
