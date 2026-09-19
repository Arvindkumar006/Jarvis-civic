/**
 * Typed API Client for JARVIS Civic.
 * Communicates strictly with backend endpoints using zero-cost, local architecture.
 */

import {
  AuditEvent,
  CaseHistoryItem,
  CitizenResolutionAcceptRequest,
  CitizenResolutionRejectRequest,
  CivicCaseCreateRequest,
  CivicCaseRecord,
  CivicEvidenceType,
  ConversationRequest,
  ConversationResponse,
  EvidenceMetadata,
  EvidenceResponse,
  PublicTrackingProjection,
  ResolutionNoteRequest,
  StatusTransitionRequest,
  AuthenticatedUser,
  LoginCredentials,
} from '../types/civic';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  public statusCode?: number;
  public details?: unknown;

  constructor(message: string, statusCode?: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

function buildSimulatedHeaders(
  role?: string,
  principalId?: string,
  dept?: string
): Record<string, string> {
  const headers: Record<string, string> = {};
  if (role) {
    headers['X-Simulated-Role'] = role;
    headers['X-Principal-Role'] = role;
  }
  if (principalId) {
    headers['X-Simulated-Principal-Id'] = principalId;
    headers['X-Principal-Id'] = principalId;
  }
  if (dept) {
    headers['X-Simulated-Department'] = dept;
    headers['X-Principal-Department'] = dept;
  }
  return headers;
}

type UnauthorizedListener = (detail?: string) => void;
const unauthorizedListeners: Set<UnauthorizedListener> = new Set();

export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export function notifyUnauthorized(detail?: string): void {
  unauthorizedListeners.forEach((listener) => {
    try {
      listener(detail);
    } catch {
      // ignore listener error
    }
  });
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = 'An error occurred while communicating with JARVIS Civic.';
    let rawDetail = '';
    try {
      const errorJson = await response.json();
      if (typeof errorJson.detail === 'string') {
        errorMessage = errorJson.detail;
        rawDetail = errorJson.detail;
      } else if (Array.isArray(errorJson.detail)) {
        errorMessage = errorJson.detail.map((e: { msg?: string }) => e.msg || 'Validation error').join(', ');
        rawDetail = errorMessage;
      }
    } catch {
      errorMessage = response.statusText || `Request failed with status ${response.status}`;
    }

    if (response.status === 401) {
      errorMessage = rawDetail || 'Session has expired or is invalid. Please log in again.';
      // Notify listeners unless this is an auth verification or login request
      if (!response.url.includes('/api/auth/login') && !response.url.includes('/api/auth/me')) {
        notifyUnauthorized(errorMessage);
      }
    } else if (response.status === 403) {
      errorMessage = rawDetail || 'Authorization denied by Cedar policy enforcement.';
    } else if (response.status === 404) {
      errorMessage = rawDetail || 'The requested civic record could not be found.';
    } else if (response.status === 409) {
      errorMessage = rawDetail || 'Invalid lifecycle transition requested.';
    } else if (response.status === 413) {
      errorMessage = 'Evidence file exceeds the maximum allowed 10MB limit.';
    } else if (response.status === 500) {
      errorMessage = 'JARVIS Civic reasoning service encountered a temporary error. Please retry.';
    }

    throw new ApiError(errorMessage, response.status);
  }

  return response.json() as Promise<T>;
}

export const conversationApi = {
  /**
   * Submit citizen problem statement or voice transcript to multi-agent reasoning loop.
   */
  async intake(request: ConversationRequest): Promise<ConversationResponse> {
    try {
      const res = await fetch(`${BASE_URL}/api/conversation`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(request),
      });
      return await handleResponse<ConversationResponse>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError(
        'Unable to connect to JARVIS Civic backend. Ensure the server is running on ' + BASE_URL,
        0
      );
    }
  },
};

export const casesApi = {
  /**
   * Persist a finalized civic action docket as an application record.
   * Protected by Cedar (Action: create_case).
   */
  async createCase(
    payload: CivicCaseCreateRequest,
    principalId: string = 'cit-user-1'
  ): Promise<CivicCaseRecord> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Principal-Id': principalId,
          'X-Principal-Role': 'CITIZEN',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      return await handleResponse<CivicCaseRecord>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Case creation failed due to network unavailability.', 0);
    }
  },

  /**
   * Retrieve full civic case details.
   * Protected by Cedar (Action: read_own_case or read_authority_case).
   */
  async getCase(
    caseId: string,
    role?: string,
    principalId?: string,
    dept?: string
  ): Promise<CivicCaseRecord> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}`, {
        method: 'GET',
        headers: buildSimulatedHeaders(role, principalId, dept),
        credentials: 'include',
      });
      return await handleResponse<CivicCaseRecord>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Failed to retrieve case details.', 0);
    }
  },

  /**
   * Update case status along the canonical single-step lifecycle.
   * Protected by Cedar (Action: update_case_status).
   */
  async updateStatus(
    caseId: string,
    payload: StatusTransitionRequest,
    role?: string,
    principalId?: string,
    dept?: string
  ): Promise<CivicCaseRecord> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...buildSimulatedHeaders(role, principalId, dept),
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      return await handleResponse<CivicCaseRecord>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Status update failed.', 0);
    }
  },

  /**
   * Add an authority resolution note to the case.
   * Protected by Cedar (Action: add_resolution_note).
   */
  async addResolutionNote(
    caseId: string,
    payload: ResolutionNoteRequest,
    role?: string,
    principalId?: string,
    dept?: string
  ): Promise<CivicCaseRecord> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/resolution-note`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...buildSimulatedHeaders(role, principalId, dept),
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      return await handleResponse<CivicCaseRecord>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Adding resolution note failed.', 0);
    }
  },

  /**
   * Retrieve sanitized lifecycle history milestones.
   */
  async getHistory(
    caseId: string,
    role?: string,
    principalId?: string,
    dept?: string
  ): Promise<CaseHistoryItem[]> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/history`, {
        method: 'GET',
        headers: buildSimulatedHeaders(role, principalId, dept),
        credentials: 'include',
      });
      return await handleResponse<CaseHistoryItem[]>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Failed to fetch case history.', 0);
    }
  },

  /**
   * Citizen accepts resolution and closes case directly to RESOLVED.
   * Protected by Cedar (Action: accept_resolution).
   *
   * SECURITY: Identity is resolved exclusively from the authenticated server-side
   * session cookie. No simulation headers are sent. Do not add role/principal
   * parameters to this method — citizen-only closure must never accept client identity.
   */
  async acceptResolution(
    caseId: string,
    payload: CitizenResolutionAcceptRequest = {}
  ): Promise<CivicCaseRecord> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/resolution/accept`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      return await handleResponse<CivicCaseRecord>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Resolution acceptance failed.', 0);
    }
  },

  /**
   * Citizen rejects resolution with mandatory reason, returning docket for rework.
   * Protected by Cedar (Action: reject_resolution).
   *
   * SECURITY: Identity is resolved exclusively from the authenticated server-side
   * session cookie. No simulation headers are sent. Do not add role/principal
   * parameters to this method — citizen-only closure must never accept client identity.
   */
  async rejectResolution(
    caseId: string,
    payload: CitizenResolutionRejectRequest
  ): Promise<CivicCaseRecord> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/resolution/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      return await handleResponse<CivicCaseRecord>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Resolution rejection failed.', 0);
    }
  },
};

export const auditApi = {
  /**
   * Retrieve Cedar-protected audit trail for a case.
   * Protected by Cedar (Action: read_audit_log).
   */
  async getCaseAuditTrail(
    caseId: string,
    role?: string,
    principalId?: string,
    dept?: string
  ): Promise<AuditEvent[]> {
    try {
      const res = await fetch(`${BASE_URL}/api/audit/cases/${encodeURIComponent(caseId)}`, {
        method: 'GET',
        headers: buildSimulatedHeaders(role, principalId, dept),
        credentials: 'include',
      });
      return await handleResponse<AuditEvent[]>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Audit trail query failed.', 0);
    }
  },

  /**
   * Retrieve all audit events (for administrators/supervisors).
   */
  async getAuditLogs(
    role?: string,
    principalId?: string,
    dept?: string
  ): Promise<AuditEvent[]> {
    try {
      const res = await fetch(`${BASE_URL}/api/audit/logs`, {
        method: 'GET',
        headers: buildSimulatedHeaders(role, principalId, dept),
        credentials: 'include',
      });
      return await handleResponse<AuditEvent[]>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Audit logs query failed.', 0);
    }
  },
};

export const evidenceApi = {
  /**
   * Upload and attach evidence to a civic case.
   * Protected by Cedar (Action: add_evidence vs add_resolution_evidence).
   */
  async uploadEvidence(
    caseId: string,
    file: File,
    role?: string,
    principalId?: string,
    dept?: string,
    evidenceType: CivicEvidenceType = CivicEvidenceType.CASE_EVIDENCE,
    resolutionAttempt?: string
  ): Promise<EvidenceResponse> {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('evidence_type', evidenceType);
      if (resolutionAttempt) {
        formData.append('resolution_attempt', resolutionAttempt);
      }

      const simHeaders = buildSimulatedHeaders(role, principalId, dept);
      const headers: Record<string, string> = {
        'X-Principal-Id': principalId || 'cit-user-1',
        'X-Principal-Role': role || 'CITIZEN',
        ...simHeaders,
      };

      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/evidence`, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: formData,
      });
      return await handleResponse<EvidenceResponse>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Evidence upload failed due to network error.', 0);
    }
  },

  /**
   * Retrieve verified evidence records for a case.
   * Protected by Cedar (Action: read_evidence).
   */
  async listEvidence(caseId: string): Promise<EvidenceResponse[]> {
    try {
      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/evidence`, {
        method: 'GET',
        credentials: 'include',
      });
      return await handleResponse<EvidenceResponse[]>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Failed to retrieve case evidence.', 0);
    }
  },
};

export const trackingApi = {
  /**
   * Retrieve public-safe tracking projection.
   * Does NOT expose private citizen details or internal auth logs.
   */
  async getTracking(caseId: string): Promise<PublicTrackingProjection> {
    try {
      const res = await fetch(`${BASE_URL}/api/tracking/${encodeURIComponent(caseId)}`, {
        method: 'GET',
        credentials: 'include',
      });
      return await handleResponse<PublicTrackingProjection>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Tracking query failed due to network unavailability.', 0);
    }
  },
};

export const healthApi = {
  /**
   * Health check to detect backend liveness.
   */
  async checkHealth(): Promise<boolean> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(`${BASE_URL}/api/health`, {
        method: 'GET',
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return res.ok;
    } catch {
      return false;
    }
  },
};

export const authApi = {
  /**
   * Authenticate user credentials server-side and establish HttpOnly session cookie.
   */
  async login(credentials: LoginCredentials): Promise<AuthenticatedUser> {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(credentials),
      });
      return await handleResponse<AuthenticatedUser>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Authentication request failed due to network unavailability.', 0);
    }
  },

  /**
   * Retrieve active authenticated account identity resolved from session cookie.
   */
  async me(): Promise<AuthenticatedUser> {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/me`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });
      return await handleResponse<AuthenticatedUser>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Failed to verify session identity with backend.', 0);
    }
  },

  /**
   * Invalidate active session and clear session cookie.
   */
  async logout(): Promise<{ detail: string }> {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });
      return await handleResponse<{ detail: string }>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Logout request failed due to network unavailability.', 0);
    }
  },
};

export const api = {
  intakeConversation: conversationApi.intake,
  createCase: casesApi.createCase,
  getCase: casesApi.getCase,
  updateCaseStatus: casesApi.updateStatus,
  addResolutionNote: casesApi.addResolutionNote,
  getCaseHistory: casesApi.getHistory,
  getCaseAuditTrail: auditApi.getCaseAuditTrail,
  uploadEvidence: evidenceApi.uploadEvidence,
  getPublicTracking: trackingApi.getTracking,
  checkHealth: healthApi.checkHealth,
  authLogin: authApi.login,
  authMe: authApi.me,
  authLogout: authApi.logout,
  acceptResolution: casesApi.acceptResolution,
  rejectResolution: casesApi.rejectResolution,
};

