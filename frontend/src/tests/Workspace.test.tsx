import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { WorkspaceProvider, useWorkspace } from '../context/WorkspaceContext';
import { WorkspaceSelector } from '../components/Workspace/WorkspaceSelector';
import { Navbar } from '../components/Layout/Navbar';
import { ApplicationRole, ControlledDepartment } from '../types/civic';

describe('Workspace System', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders all 5 civic workspaces in WorkspaceSelector', () => {
    render(
      <WorkspaceProvider>
        <WorkspaceSelector />
      </WorkspaceProvider>
    );

    expect(screen.getByText('WHO IS ACCESSING JARVIS CIVIC?')).toBeInTheDocument();
    expect(screen.getByText('CITIZEN WORKSPACE')).toBeInTheDocument();
    expect(screen.getByText('AUTHORITY OFFICER WORKSPACE')).toBeInTheDocument();
    expect(screen.getByText('MUNICIPAL SUPERVISOR WORKSPACE')).toBeInTheDocument();
    expect(screen.getByText('ADMINISTRATOR WORKSPACE')).toBeInTheDocument();
    expect(screen.getByText('PUBLIC TRACKING')).toBeInTheDocument();
  });

  it('immediately switches to Citizen workspace on click', () => {
    const TestConsumer = () => {
      const { session } = useWorkspace();
      return <div data-testid="active-role">{session.role}</div>;
    };

    render(
      <WorkspaceProvider initialRole={ApplicationRole.PUBLIC}>
        <WorkspaceSelector />
        <TestConsumer />
      </WorkspaceProvider>
    );

    const citizenCardBtn = screen.getByRole('button', { name: /Enter CITIZEN WORKSPACE/i });
    fireEvent.click(citizenCardBtn);

    expect(screen.getByTestId('active-role')).toHaveTextContent(ApplicationRole.CITIZEN);
  });

  it('prompts for department selection when Authority Officer is chosen', () => {
    render(
      <WorkspaceProvider initialRole={ApplicationRole.CITIZEN}>
        <WorkspaceSelector />
      </WorkspaceProvider>
    );

    const authBtn = screen.getByRole('button', { name: /Enter AUTHORITY OFFICER WORKSPACE/i });
    fireEvent.click(authBtn);

    // Should transition to step 2 configuration
    expect(screen.getByText('Configure Authority Department & Identity')).toBeInTheDocument();
    expect(screen.getByLabelText(/ASSIGNED DEPARTMENT JURISDICTION/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/LOCAL SIMULATION IDENTITY/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Server-side Cedar policies remain authoritative/i)
    ).toBeInTheDocument();
  });

  it('confirms authority department and updates workspace session', () => {
    const TestConsumer = () => {
      const { session } = useWorkspace();
      return (
        <div>
          <span data-testid="role">{session.role}</span>
          <span data-testid="dept">{session.department}</span>
          <span data-testid="pid">{session.principalId}</span>
        </div>
      );
    };

    render(
      <WorkspaceProvider initialRole={ApplicationRole.CITIZEN}>
        <WorkspaceSelector />
        <TestConsumer />
      </WorkspaceProvider>
    );

    // Click Authority Officer
    fireEvent.click(screen.getByRole('button', { name: /Enter AUTHORITY OFFICER WORKSPACE/i }));

    // Change department to PWD_ROADS
    const deptSelect = screen.getByLabelText(/ASSIGNED DEPARTMENT JURISDICTION/i);
    fireEvent.change(deptSelect, { target: { value: ControlledDepartment.PWD_ROADS } });

    // Submit configuration
    const submitBtn = screen.getByRole('button', { name: /ENTER AUTHORITY CONSOLE/i });
    fireEvent.click(submitBtn);

    expect(screen.getByTestId('role')).toHaveTextContent(ApplicationRole.AUTHORITY_OFFICER);
    expect(screen.getByTestId('dept')).toHaveTextContent(ControlledDepartment.PWD_ROADS);
  });

  it('adapts Navbar dynamically based on active workspace role', () => {
    const onSelectTab = vi.fn();

    // 1. Citizen Navbar
    const { rerender } = render(
      <WorkspaceProvider initialRole={ApplicationRole.CITIZEN}>
        <Navbar
          activeTab="report"
          onSelectTab={onSelectTab}
          backendOnline={true}
          docketCount={0}
        />
      </WorkspaceProvider>
    );

    expect(screen.getByRole('button', { name: /Report Issue/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Track Docket/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Evidence Studio/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Authority Console/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Audit Trail/i })).not.toBeInTheDocument();

    // 2. Public Tracking Navbar
    rerender(
      <WorkspaceProvider initialRole={ApplicationRole.PUBLIC}>
        <Navbar
          activeTab="track"
          onSelectTab={onSelectTab}
          backendOnline={true}
          docketCount={0}
        />
      </WorkspaceProvider>
    );

    expect(screen.getByRole('button', { name: /Public Tracking/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Report Issue/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Evidence Studio/i })).not.toBeInTheDocument();

    // 3. Supervisor Navbar
    rerender(
      <WorkspaceProvider
        initialRole={ApplicationRole.MUNICIPAL_SUPERVISOR}
        initialDepartment={ControlledDepartment.DRAINAGE_STORMWATER}
      >
        <Navbar
          activeTab="console"
          onSelectTab={onSelectTab}
          backendOnline={true}
          docketCount={0}
        />
      </WorkspaceProvider>
    );

    expect(screen.getByRole('button', { name: /Supervisor Console/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Track Docket/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Evidence/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Audit Trail/i })).toBeInTheDocument();
  });
});
