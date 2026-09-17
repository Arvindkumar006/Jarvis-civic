import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { App } from '../App';
import { healthApi, conversationApi } from '../services/api';

vi.mock('../services/api', () => ({
  healthApi: {
    checkHealth: vi.fn(),
  },
  conversationApi: {
    intake: vi.fn(),
  },
  casesApi: {
    createCase: vi.fn(),
  },
  trackingApi: {
    getTracking: vi.fn(),
  },
  evidenceApi: {
    uploadEvidence: vi.fn(),
  },
}));

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(healthApi.checkHealth).mockResolvedValue(true);
  });

  it('renders JARVIS Civic branding, tagline, and navigation tabs', async () => {
    render(<App />);

    expect(screen.getByText('JARVIS')).toBeInTheDocument();
    expect(screen.getByText('CIVIC')).toBeInTheDocument();
    expect(screen.getByText('Speak. Report. Resolve.')).toBeInTheDocument();
    expect(screen.getByText(/Prototype • Not a Government Portal/i)).toBeInTheDocument();

    expect(screen.getByRole('button', { name: /Report Issue/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Track Docket/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Evidence Studio/i })).toBeInTheDocument();
  });

  it('switches between tabs on navigation click', async () => {
    render(<App />);

    // Click Track Docket
    const trackTab = screen.getByRole('button', { name: /Track Docket/i });
    fireEvent.click(trackTab);

    expect(screen.getByText('Track Civic Action Docket')).toBeInTheDocument();

    // Click Evidence Studio
    const evidenceTab = screen.getByRole('button', { name: /Evidence Studio/i });
    fireEvent.click(evidenceTab);

    expect(screen.getByText('Evidence Attachment Studio')).toBeInTheDocument();
  });

  it('populates conversation when a quick prompt is clicked from hero', async () => {
    vi.mocked(conversationApi.intake).mockResolvedValueOnce({
      reply: 'I have logged the waterlogging report at Anna Salai. Is this near the Thousand Lights metro?',
      state: {
        intent: 'WATERLOGGING_DRAINAGE_DEFECT',
        department: 'DRAINAGE_STORMWATER' as any,
        location: 'Anna Salai',
        landmark: null,
        pincode: null,
        urgency: 'HIGH' as any,
        urgency_rationale: 'Active road flood',
        language: 'en-IN',
        confidence: 0.95,
        description: 'Severe waterlogging at Anna Salai',
      },
      missing_fields: ['landmark', 'pincode'],
    });

    render(<App />);

    const quickPrompt = screen.getByText('Waterlogging');
    fireEvent.click(quickPrompt);

    await waitFor(() => {
      expect(conversationApi.intake).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/I have logged the waterlogging report/i)).toBeInTheDocument();
    });
  });

  it('navigates to Page 01 Product Experience and returns to report via CTA', async () => {
    render(<App />);

    // Click brand lockup button to view Page 01 Product Experience
    const brandBtn = screen.getByRole('button', { name: /JARVIS Civic Home Experience/i });
    fireEvent.click(brandBtn);

    expect(screen.getByText(/How JARVIS Works/i)).toBeInTheDocument();
    expect(screen.getByText(/Speak in Your Mother Tongue/i)).toBeInTheDocument();
    expect(screen.getByText(/Modern Architectural Stack/i)).toBeInTheDocument();

    // Click CTA button START A CIVIC REPORT
    const startReportBtn = screen.getAllByRole('button', { name: /START A CIVIC REPORT/i })[0];
    fireEvent.click(startReportBtn);

    // Returned to Page 02 Report Studio
    expect(screen.getByText('Tell us what needs attention.')).toBeInTheDocument();
  });
});
