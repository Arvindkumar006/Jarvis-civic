import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ExtractionHUD } from '../components/HUD/ExtractionHUD';
import { CanonicalCivicState, CivicIntent, ControlledDepartment, UrgencyLevel } from '../types/civic';

describe('ExtractionHUD', () => {
  it('renders initial waiting state when state is null', () => {
    const onOpen = vi.fn();
    render(<ExtractionHUD state={null} onOpenDocketReview={onOpen} />);

    expect(screen.getByText(/Civic Extraction HUD/i)).toBeInTheDocument();
    expect(screen.getByText(/Listening for problem statement/i)).toBeInTheDocument();
  });

  it('renders extracted civic parameters and missing field checklist', () => {
    const onOpen = vi.fn();
    const partialState: CanonicalCivicState = {
      intent: CivicIntent.WATERLOGGING,
      department: ControlledDepartment.DRAINAGE_STORMWATER,
      location: 'Anna Salai',
      landmark: null,
      pincode: null,
      urgency: UrgencyLevel.HIGH,
      urgency_rationale: 'Active road flood',
      language: 'ta-IN',
      confidence: 0.92,
      description: 'Waterlogging at Anna Salai',
      missing_fields: ['landmark', 'pincode'],
      ready_for_action: false,
    };

    render(<ExtractionHUD state={partialState} onOpenDocketReview={onOpen} />);

    // Recommended department
    expect(screen.getByText(/Drainage & Stormwater/i)).toBeInTheDocument();
    expect(screen.getByText(/Anna Salai/i)).toBeInTheDocument();
    expect(screen.getByText(/HIGH/i)).toBeInTheDocument();
    expect(screen.getByText(/ta-IN/i)).toBeInTheDocument();
    expect(screen.getByText(/92%/i)).toBeInTheDocument();

    // Missing field alert
    expect(screen.getByText(/Missing Information/i)).toBeInTheDocument();
    expect(screen.getAllByText(/landmark/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Please specify:/i).length).toBe(2);
  });

  it('enables docket review button when ready for action', () => {
    const onOpen = vi.fn();
    const completeState: CanonicalCivicState = {
      intent: CivicIntent.ROAD_POTHOLE,
      department: ControlledDepartment.PWD_ROADS,
      location: 'MG Road, Bangalore',
      landmark: 'Near Railway Station',
      pincode: '560001',
      urgency: UrgencyLevel.CRITICAL,
      urgency_rationale: 'Accidents reported',
      language: 'kn-IN',
      confidence: 0.98,
      description: 'Deep road crater causing bike crashes.',
      missing_fields: [],
      ready_for_action: true,
    };

    render(<ExtractionHUD state={completeState} onOpenDocketReview={onOpen} />);

    expect(screen.getByText(/Ready for Action/i)).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: /Review & Generate Docket/i });
    expect(btn).not.toBeDisabled();

    fireEvent.click(btn);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});
