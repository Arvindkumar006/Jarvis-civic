import React, { createContext, useContext, useState, useMemo, useCallback, useEffect } from 'react';
import { ApplicationRole, ControlledDepartment } from '../types/civic';
import { useAuth } from './AuthContext';

export interface WorkspaceSession {
  role: ApplicationRole;
  principalId: string;
  department?: ControlledDepartment;
  label: string;
  description: string;
}

export const DEFAULT_PRINCIPALS: Record<ApplicationRole, string> = {
  [ApplicationRole.CITIZEN]: 'citizen-01',
  [ApplicationRole.AUTHORITY_OFFICER]: 'authority-officer-01',
  [ApplicationRole.MUNICIPAL_SUPERVISOR]: 'supervisor-01',
  [ApplicationRole.ADMINISTRATOR]: 'admin-01',
  [ApplicationRole.PUBLIC]: 'public-anonymous',
};

export const WORKSPACE_METADATA: Record<
  ApplicationRole,
  { label: string; description: string; capabilities: string[] }
> = {
  [ApplicationRole.CITIZEN]: {
    label: 'CITIZEN WORKSPACE',
    description:
      'Report civic issues, create structured Civic Action Dockets, attach evidence and track progress.',
    capabilities: ['Report Issue', 'Track Docket', 'Evidence Studio'],
  },
  [ApplicationRole.AUTHORITY_OFFICER]: {
    label: 'AUTHORITY OFFICER WORKSPACE',
    description:
      'Review department-scoped civic dockets and perform authorized workflow actions.',
    capabilities: [
      'Authority Console',
      'Assigned Dockets',
      'Evidence Studio',
      'Authorized workflow actions',
    ],
  },
  [ApplicationRole.MUNICIPAL_SUPERVISOR]: {
    label: 'MUNICIPAL SUPERVISOR WORKSPACE',
    description:
      'Supervise department-scoped civic workflows and inspect authorized audit information.',
    capabilities: [
      'Supervisor Console',
      'Track Docket',
      'Evidence Studio',
      'Audit Trail',
    ],
  },
  [ApplicationRole.ADMINISTRATOR]: {
    label: 'ADMINISTRATOR WORKSPACE',
    description:
      'Access the administrative civic workflow and authorized audit surfaces.',
    capabilities: [
      'Admin Console',
      'Track Docket',
      'Evidence Studio',
      'Audit Trail',
    ],
  },
  [ApplicationRole.PUBLIC]: {
    label: 'PUBLIC TRACKING',
    description:
      'Track publicly available civic docket information without an authenticated authority workspace.',
    capabilities: ['Public-safe tracking only'],
  },
};

interface WorkspaceContextValue {
  session: WorkspaceSession;
  isSelectingWorkspace: boolean;
  selectWorkspace: (role: ApplicationRole, department?: ControlledDepartment, customPrincipalId?: string) => void;
  switchWorkspace: () => void;
  cancelWorkspaceSwitch: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

function buildSession(
  role: ApplicationRole,
  department?: ControlledDepartment,
  principalId?: string
): WorkspaceSession {
  const meta = WORKSPACE_METADATA[role] || WORKSPACE_METADATA[ApplicationRole.PUBLIC];
  const pid = principalId && principalId.trim() ? principalId.trim() : DEFAULT_PRINCIPALS[role];
  const dept =
    role === ApplicationRole.AUTHORITY_OFFICER || role === ApplicationRole.MUNICIPAL_SUPERVISOR
      ? department || ControlledDepartment.DRAINAGE_STORMWATER
      : undefined;

  return {
    role,
    principalId: pid,
    department: dept,
    label: meta.label,
    description: meta.description,
  };
}

export const WorkspaceProvider: React.FC<{
  children: React.ReactNode;
  initialRole?: ApplicationRole;
  initialDepartment?: ControlledDepartment;
  initialPrincipalId?: string;
}> = ({ children, initialRole, initialDepartment, initialPrincipalId }) => {
  // Gracefully attempt to consume AuthContext
  let auth: ReturnType<typeof useAuth> | null = null;
  try {
    auth = useAuth();
  } catch {
    auth = null;
  }

  // Local fallback session when mounted outside AuthProvider (e.g., standalone component tests)
  const [localSession, setLocalSession] = useState<WorkspaceSession>(() => {
    if (initialRole) {
      return buildSession(initialRole, initialDepartment, initialPrincipalId);
    }
    return buildSession(ApplicationRole.CITIZEN);
  });

  useEffect(() => {
    if (initialRole) {
      setLocalSession(buildSession(initialRole, initialDepartment, initialPrincipalId));
    }
  }, [initialRole, initialDepartment, initialPrincipalId]);

  // Derive session strictly from AuthContext when available
  const session: WorkspaceSession = useMemo(() => {
    if (auth) {
      if (auth.isAuthenticated && auth.user) {
        const activeRole = auth.user.role;
        const meta = WORKSPACE_METADATA[activeRole] || WORKSPACE_METADATA[ApplicationRole.PUBLIC];
        return {
          role: activeRole,
          principalId: auth.user.principal_id,
          department: (auth.user.department as ControlledDepartment) || undefined,
          label: meta.label,
          description: meta.description,
        };
      }
      const meta = WORKSPACE_METADATA[ApplicationRole.PUBLIC];
      return {
        role: ApplicationRole.PUBLIC,
        principalId: 'public-anonymous',
        department: undefined,
        label: meta.label,
        description: meta.description,
      };
    }
    return localSession;
  }, [auth?.isAuthenticated, auth?.user, localSession]);

  const [isSelectingWorkspace, setIsSelectingWorkspace] = useState<boolean>(false);

  const selectWorkspace = useCallback(
    (role: ApplicationRole, dept?: ControlledDepartment, customPrincipalId?: string) => {
      if (auth) {
        auth.openLogin(role);
      } else {
        setLocalSession(buildSession(role, dept, customPrincipalId));
      }
      setIsSelectingWorkspace(false);
    },
    [auth]
  );

  const switchWorkspace = useCallback(() => {
    if (auth) {
      auth.openLogin();
    } else {
      setIsSelectingWorkspace(true);
    }
  }, [auth]);

  const cancelWorkspaceSwitch = useCallback(() => {
    setIsSelectingWorkspace(false);
    if (auth) {
      auth.closeLogin();
    }
  }, [auth]);

  const value = useMemo(
    () => ({
      session,
      isSelectingWorkspace,
      selectWorkspace,
      switchWorkspace,
      cancelWorkspaceSwitch,
    }),
    [session, isSelectingWorkspace, selectWorkspace, switchWorkspace, cancelWorkspaceSwitch]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
};

const defaultPublicSession = buildSession(ApplicationRole.PUBLIC);
const defaultFallbackContext: WorkspaceContextValue = {
  session: defaultPublicSession,
  isSelectingWorkspace: false,
  selectWorkspace: () => {},
  switchWorkspace: () => {},
  cancelWorkspaceSwitch: () => {},
};

export const useWorkspace = (): WorkspaceContextValue => {
  const context = useContext(WorkspaceContext);
  if (!context) {
    return defaultFallbackContext;
  }
  return context;
};
