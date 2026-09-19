import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { ApplicationRole, AuthenticatedUser, ControlledDepartment, LoginCredentials } from '../types/civic';
import { authApi, onUnauthorized } from '../services/api';

export interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: AuthenticatedUser | null;
  role: ApplicationRole;
  principalId: string;
  email: string;
  displayName: string;
  department: ControlledDepartment | string | null;
  sessionExpiredMessage: string | null;
  isLoginOpen: boolean;
  intendedRole: ApplicationRole | null;
  login: (credentials: LoginCredentials) => Promise<AuthenticatedUser>;
  logout: () => Promise<void>;
  openLogin: (role?: ApplicationRole) => void;
  closeLogin: () => void;
  clearSessionExpiredMessage: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{
  children: React.ReactNode;
  initialUser?: AuthenticatedUser | null;
  skipInitialCheck?: boolean;
}> = ({ children, initialUser, skipInitialCheck = false }) => {
  const [user, setUser] = useState<AuthenticatedUser | null>(initialUser ?? null);
  const [isLoading, setIsLoading] = useState<boolean>(!skipInitialCheck && initialUser === undefined);
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);
  const [isLoginOpen, setIsLoginOpen] = useState<boolean>(false);
  const [intendedRole, setIntendedRole] = useState<ApplicationRole | null>(null);

  // Bootstrap: Check active session with backend via GET /api/auth/me
  const checkSession = useCallback(async () => {
    try {
      setIsLoading(true);
      const currentUser = await authApi.me();
      if (currentUser && currentUser.is_active !== false) {
        setUser(currentUser);
        setSessionExpiredMessage(null);
      } else {
        setUser(null);
      }
    } catch {
      // 401 Unauthorized or network failure means user is unauthenticated
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!skipInitialCheck && initialUser === undefined) {
      checkSession();
    }
  }, [checkSession, skipInitialCheck, initialUser]);

  // Subscribe to API 401 events for automatic session expiration handling
  useEffect(() => {
    const unsubscribe = onUnauthorized((detail) => {
      setUser(null);
      setSessionExpiredMessage(detail || 'Session has expired or is invalid. Please log in again.');
      setIsLoginOpen(true);
    });
    return unsubscribe;
  }, []);

  const login = useCallback(async (credentials: LoginCredentials): Promise<AuthenticatedUser> => {
    setIsLoading(true);
    try {
      // 1. Authenticate with backend and establish HttpOnly session cookie
      await authApi.login(credentials);
      // 2. Fetch authoritative identity strictly from GET /api/auth/me
      const activeUser = await authApi.me();
      setUser(activeUser);
      setSessionExpiredMessage(null);
      setIsLoginOpen(false);
      setIntendedRole(null);
      return activeUser;
    } catch (err) {
      setUser(null);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      await authApi.logout();
    } catch {
      // Safe to ignore backend logout error, ensure client state is cleared
    } finally {
      setUser(null);
      setIntendedRole(null);
      setIsLoading(false);
    }
  }, []);

  const openLogin = useCallback((role?: ApplicationRole) => {
    setIntendedRole(role || null);
    setIsLoginOpen(true);
  }, []);

  const closeLogin = useCallback(() => {
    setIsLoginOpen(false);
  }, []);

  const clearSessionExpiredMessage = useCallback(() => {
    setSessionExpiredMessage(null);
  }, []);

  // Derived properties from backend-authoritative identity
  const isAuthenticated = Boolean(user && user.is_active);
  const role = user?.role || ApplicationRole.PUBLIC;
  const principalId = user?.principal_id || (isAuthenticated ? '' : 'public-anonymous');
  const email = user?.email || '';
  const displayName = user?.display_name || (isAuthenticated ? '' : 'Anonymous Visitor');
  const department = user?.department || null;

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      isLoading,
      user,
      role,
      principalId,
      email,
      displayName,
      department,
      sessionExpiredMessage,
      isLoginOpen,
      intendedRole,
      login,
      logout,
      openLogin,
      closeLogin,
      clearSessionExpiredMessage,
    }),
    [
      isAuthenticated,
      isLoading,
      user,
      role,
      principalId,
      email,
      displayName,
      department,
      sessionExpiredMessage,
      isLoginOpen,
      intendedRole,
      login,
      logout,
      openLogin,
      closeLogin,
      clearSessionExpiredMessage,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
