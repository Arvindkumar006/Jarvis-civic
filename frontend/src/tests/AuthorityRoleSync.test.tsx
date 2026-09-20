import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ProductExperience } from '../components/Experience/ProductExperience';
import { TrackingView } from '../components/Tracking/TrackingView';
import { WorkspaceProvider } from '../context/WorkspaceContext';
import { AuthProvider } from '../context/AuthContext';
import { trackingApi, casesApi } from '../services/api';
import { ApplicationRole, CaseStatus, ControlledDepartment, CivicCaseRecord, PublicTrackingProjection } from '../types/civic';

// Mock the APIs
vi.mock('../services/api', () => ({
  onUnauthorized: vi.fn(() => () => {}),
  authApi: {
    login: vi.fn(),
    me: vi.fn().mockResolvedValue({
      principal_id: 'citizen-01',
      role: 'CITIZEN',
      display_name: 'Citizen User',
      email: 'citizen@jarviscivic.local',
      department: null,
      is_active: true,
      last_active_at: new Date().toISOString(),
    }),
    logout: vi.fn(),
  },
  trackingApi: {
    getTracking: vi.fn(),
  },
  casesApi: {
    getCase: vi.fn(),
    updateStatus: vi.fn(),
    addResolutionNote: vi.fn(),
    getHistory: vi.fn().mockResolvedValue([]),
    acceptResolution: vi.fn(),
    rejectResolution: vi.fn(),
  },
  evidenceApi: {
    listEvidence: vi.fn().mockResolvedValue([]),
    uploadEvidence: vi.fn(),
  },
  auditApi: {
    getCaseAuditTrail: vi.fn().mockResolvedValue([]),
  },
}));

// Mock CivicMap to avoid Leaflet DOM issues
vi.mock('../components/Map/CivicMap', () => ({
  CivicMap: () => <div data-testid="mock-civic-map">CivicMap</div>,
  getApproxCoordinates: () => [13.0827, 80.2707],
}));

describe('Authority Workspace Roles & Docket Synchronization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  // ===========================================================================
  // 1. PRODUCT WORKSPACE ARCHITECTURE: 4 DOMAINS & STRICT 5-ROLE AUTHORITY
  // ===========================================================================
  describe('ProductExperience Workspace Presentation', () => {
    it('renders all 4 architectural domains', () => {
      render(
        <AuthProvider>
          <WorkspaceProvider>
            <ProductExperience onStartReport={() => {}} onExploreTrack={() => {}} />
          </WorkspaceProvider>
        </AuthProvider>
      );

      expect(screen.getByText('DOMAIN 01 // CITIZEN WORKSPACE')).toBeInTheDocument();
      expect(screen.getByText('DOMAIN 02 // AUTHORITY WORKSPACE (OPERATIONAL ROLES ONLY)')).toBeInTheDocument();
      expect(screen.getByText('DOMAIN 03 // PUBLIC TRACKING')).toBeInTheDocument();
      expect(screen.getByText('DOMAIN 04 // ADMINISTRATIVE CONTROL PLANE (NOT AN AUTHORITY ROLE)')).toBeInTheDocument();
    });

    it('Authority Workspace domain contains EXACTLY the 5 operational authority roles', () => {
      render(
        <AuthProvider>
          <WorkspaceProvider>
            <ProductExperience onStartReport={() => {}} onExploreTrack={() => {}} />
          </WorkspaceProvider>
        </AuthProvider>
      );

      // Verify the 5 operational roles exist
      expect(screen.getByTestId('role-card-authority-pwd')).toBeInTheDocument();
      expect(screen.getByTestId('role-card-authority-roads')).toBeInTheDocument();
      expect(screen.getByTestId('role-card-authority-drainage')).toBeInTheDocument();
      expect(screen.getByTestId('role-card-authority-stormwater')).toBeInTheDocument();
      expect(screen.getByTestId('role-card-supervisor')).toBeInTheDocument();

      // Verify Public is in its own domain and NOT in authority workspace
      const publicCard = screen.getByTestId('role-card-public');
      expect(publicCard).toBeInTheDocument();
      expect(publicCard.closest('.authority-5roles-grid')).toBeNull();

      // Verify System Administrator is in its own domain and NOT in authority workspace
      const adminCard = screen.getByTestId('role-card-admin');
      expect(adminCard).toBeInTheDocument();
      expect(adminCard.closest('.authority-5roles-grid')).toBeNull();
    });
  });

  // ===========================================================================
  // 2. AUTHORITATIVE DOCKET STATUS SYNCHRONIZATION
  // ===========================================================================
  describe('TrackingView Authoritative Status Synchronization', () => {
    it('displays RESOLVED across all surfaces when CaseStore returns RESOLVED', async () => {
      const mockResolvedProjection: PublicTrackingProjection = {
        case_id: 'NS-CHN-2026-RESOLVED',
        status: CaseStatus.RESOLVED,
        recommended_department: ControlledDepartment.PWD_ROADS,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const mockResolvedCase: CivicCaseRecord = {
        case_id: 'NS-CHN-2026-RESOLVED',
        description: 'Pothole on Mount Road',
        location: 'Mount Road',
        department: ControlledDepartment.PWD_ROADS,
        status: CaseStatus.RESOLVED,
        urgency: 'HIGH',
        owner_id: 'citizen-01',
        is_public: true,
        evidence_uris: [],
        resolution_notes: [],
        resolution_confirmed: true,
        resolution_confirmed_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      vi.mocked(trackingApi.getTracking).mockResolvedValue(mockResolvedProjection);
      vi.mocked(casesApi.getCase).mockResolvedValue(mockResolvedCase);

      render(
        <AuthProvider>
          <WorkspaceProvider initialRole={ApplicationRole.CITIZEN} initialPrincipalId="citizen-01">
            <TrackingView
              initialCaseId="NS-CHN-2026-RESOLVED"
              recentCaseIds={['NS-CHN-2026-RESOLVED']}
              initialMode="PUBLIC"
            />
          </WorkspaceProvider>
        </AuthProvider>
      );

      // Verify authoritative status is fetched and displayed as RESOLVED
      await waitFor(() => {
        expect(trackingApi.getTracking).toHaveBeenCalledWith('NS-CHN-2026-RESOLVED');
      });

      // Top status pill
      await waitFor(() => {
        const statusPills = screen.getAllByText('RESOLVED');
        expect(statusPills.length).toBeGreaterThan(0);
      });

      // Lifecycle step 5 should be the current/active status
      expect(screen.getAllByText('Resolved').length).toBeGreaterThan(0);
      expect(screen.getByText('Resolution recorded in the civic workflow.')).toBeInTheDocument();

      // Recent docket card should display RESOLVED, not hardcoded DOCKET CREATED
      await waitFor(() => {
        const recentCard = screen.getByLabelText(/Track recent docket NS-CHN-2026-RESOLVED/i);
        expect(recentCard).toHaveTextContent('RESOLVED');
        expect(recentCard).not.toHaveTextContent('DOCKET CREATED');
      });
    });

    it('does NOT fallback to DOCKET_CREATED when fetching an existing case that fails', async () => {
      vi.mocked(trackingApi.getTracking).mockRejectedValue(new Error('Network lookup error'));

      render(
        <AuthProvider>
          <WorkspaceProvider initialRole={ApplicationRole.CITIZEN}>
            <TrackingView
              initialCaseId="NS-CHN-2026-FAIL"
              recentCaseIds={['NS-CHN-2026-FAIL']}
              initialMode="PUBLIC"
            />
          </WorkspaceProvider>
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Case Lookup Failed')).toBeInTheDocument();
      });

      // The UI must show lookup failure error and NOT misleadingly show a DOCKET CREATED lifecycle
      expect(screen.queryByText('CURRENT STATUS')).toBeNull();
    });
  });
});
