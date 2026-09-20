import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ExtractionHUD } from '../components/HUD/ExtractionHUD';
import { ActionDocketModal } from '../components/Docket/ActionDocketModal';
import {
  CanonicalCivicState,
  CivicIntent,
  ControlledDepartment,
  UrgencyLevel,
  CivicCaseRecord,
  CaseStatus,
} from '../types/civic';

describe('Post-Creation Docket UI State and Synchronization', () => {
  const mockReadyState: CanonicalCivicState = {
    intent: CivicIntent.WATERLOGGING,
    department: ControlledDepartment.DRAINAGE_STORMWATER,
    location: 'Anna Salai, Chennai',
    landmark: 'Thousand Lights Metro',
    pincode: '600006',
    urgency: UrgencyLevel.HIGH,
    urgency_rationale: 'Active storm road flooding',
    language: 'ta-IN',
    confidence: 0.95,
    description: 'Severe waterlogging at Anna Salai',
    missing_fields: [],
    ready_for_action: true,
  };

  const mockCreatedCase: CivicCaseRecord = {
    case_id: 'CASE-2026-821F-AUTH',
    owner_id: 'citizen-local-01',
    department: 'DRAINAGE_STORMWATER',
    status: CaseStatus.DOCKET_CREATED,
    description: 'Severe waterlogging at Anna Salai',
    location: 'Anna Salai, Chennai',
    landmark: 'Thousand Lights Metro',
    pincode: '600006',
    is_public: true,
    evidence_uris: [],
    resolution_notes: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const mockResolvedCase: CivicCaseRecord = {
    ...mockCreatedCase,
    case_id: 'CASE-2026-999Z-RESOLVED',
    status: CaseStatus.RESOLVED,
    resolution_confirmed: true,
  };

  // TEST 1: Before creation: Create Civic Action Docket button visible.
  it('TEST 1: shows "CREATE CIVIC ACTION DOCKET →" button before creation when signal is validated', () => {
    const onOpen = vi.fn();
    render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={null}
        onOpenDocketReview={onOpen}
      />
    );

    expect(screen.getAllByText(/CIVIC SIGNAL VALIDATED/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/READY FOR ACTION/i)).toBeInTheDocument();

    const createBtn = screen.getByRole('button', { name: /Review & Generate Docket/i });
    expect(createBtn).toBeInTheDocument();
    expect(screen.getByText(/CREATE CIVIC ACTION DOCKET →/i)).toBeInTheDocument();
  });

  // TEST 2: Successful create API response: button disappears.
  it('TEST 2: "CREATE CIVIC ACTION DOCKET →" button disappears immediately after successful creation', () => {
    const { rerender } = render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={null}
        onOpenDocketReview={vi.fn()}
      />
    );

    // Initial state: button exists
    expect(screen.queryByText(/CREATE CIVIC ACTION DOCKET →/i)).toBeInTheDocument();

    // Rerender with successful createdCase returned from backend API
    rerender(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={mockCreatedCase}
        onOpenDocketReview={vi.fn()}
      />
    );

    // After creation: creation button must be gone
    expect(screen.queryByText(/CREATE CIVIC ACTION DOCKET →/i)).not.toBeInTheDocument();
  });

  // TEST 3: Successful creation: "CIVIC ACTION DOCKET CREATED" visible.
  it('TEST 3: displays "CIVIC ACTION DOCKET CREATED" upon successful case creation', () => {
    render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={mockCreatedCase}
        onTrackDocket={vi.fn()}
      />
    );

    expect(screen.getAllByText('CIVIC ACTION DOCKET CREATED').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/READY FOR ACTION/i)).not.toBeInTheDocument();
  });

  // TEST 4: Created case ID is displayed.
  it('TEST 4: displays the authoritative created case ID', () => {
    render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={mockCreatedCase}
        onTrackDocket={vi.fn()}
      />
    );

    expect(screen.getByText('CASE ID:')).toBeInTheDocument();
    expect(screen.getByText(mockCreatedCase.case_id)).toBeInTheDocument();
  });

  // TEST 5: Initial persisted status: DOCKET_CREATED is displayed correctly.
  it('TEST 5: displays the initial persisted status as DOCKET CREATED', () => {
    render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={mockCreatedCase}
        onTrackDocket={vi.fn()}
      />
    );

    expect(screen.getByText('STATUS:')).toBeInTheDocument();
    expect(screen.getByText('DOCKET CREATED')).toBeInTheDocument();
  });

  // TEST 6: Track Docket uses the newly created case ID.
  it('TEST 6: "TRACK DOCKET →" button invokes handler with the newly created case ID', () => {
    const onTrack = vi.fn();
    render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={mockCreatedCase}
        onTrackDocket={onTrack}
      />
    );

    const trackBtn = screen.getByRole('button', { name: /Track Docket/i });
    expect(trackBtn).toBeInTheDocument();
    expect(screen.getByText(/TRACK DOCKET →/i)).toBeInTheDocument();

    fireEvent.click(trackBtn);
    expect(onTrack).toHaveBeenCalledTimes(1);
    expect(onTrack).toHaveBeenCalledWith(mockCreatedCase.case_id);
  });

  // TEST 7: Repeated render/click cannot create duplicate docket for the same created case.
  it('TEST 7: prevents duplicate docket creation when case has already been created', () => {
    const onOpen = vi.fn();
    const onTrack = vi.fn();

    render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={mockCreatedCase}
        onOpenDocketReview={onOpen}
        onTrackDocket={onTrack}
      />
    );

    // No creation button rendered
    expect(screen.queryByText(/CREATE CIVIC ACTION DOCKET →/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Review & Generate Docket/i })).not.toBeInTheDocument();
    expect(onOpen).not.toHaveBeenCalled();
  });

  // TEST 8: API creation failure: creation button remains available.
  it('TEST 8: on API creation failure, creation action remains available in modal with error display', async () => {
    const failingSubmit = vi.fn().mockRejectedValue(new Error('Simulated network timeout'));
    const handleClose = vi.fn();

    render(
      <ActionDocketModal
        isOpen={true}
        state={mockReadyState}
        onClose={handleClose}
        onSubmitCase={failingSubmit}
      />
    );

    const submitBtn = screen.getByRole('button', { name: /Create Civic Action Docket/i });
    expect(submitBtn).toBeInTheDocument();

    // Click submit
    fireEvent.click(submitBtn);

    // Modal stays open and displays error
    await waitFor(() => {
      expect(screen.getByText(/Simulated network timeout/i)).toBeInTheDocument();
    });

    // Modal is NOT closed on failure
    expect(handleClose).not.toHaveBeenCalled();

    // Submit button is re-enabled and still available
    expect(submitBtn).not.toBeDisabled();
  });

  // TEST 9: Existing RESOLVED case: RESOLVED is displayed, never CREATE CIVIC ACTION DOCKET or DOCKET CREATED.
  it('TEST 9: for an existing RESOLVED case, renders "CIVIC ACTION DOCKET RESOLVED" and never creation or initial status', () => {
    render(
      <ExtractionHUD
        state={mockReadyState}
        createdCase={mockResolvedCase}
        onTrackDocket={vi.fn()}
      />
    );

    // Must show RESOLVED
    expect(screen.getAllByText('CIVIC ACTION DOCKET RESOLVED').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('RESOLVED')).toBeInTheDocument();
    expect(screen.getByText(mockResolvedCase.case_id)).toBeInTheDocument();

    // MUST NOT show creation or DOCKET CREATED
    expect(screen.queryByText(/CREATE CIVIC ACTION DOCKET/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/DOCKET CREATED/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/READY FOR ACTION/i)).not.toBeInTheDocument();
  });
});
