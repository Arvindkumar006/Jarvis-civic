/**
 * Typed API Client for JARVIS Civic.
 * Communicates strictly with backend endpoints using zero-cost, local architecture.
 */

import {
  AuditEvent,
  CaseHistoryItem,
  CivicCaseCreateRequest,
  CivicCaseRecord,
  ConversationRequest,
  ConversationResponse,
  EvidenceMetadata,
  PublicTrackingProjection,
  ResolutionNoteRequest,
  StatusTransitionRequest,
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

    if (response.status === 403) {
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
      });
      return await handleResponse<CaseHistoryItem[]>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Failed to fetch case history.', 0);
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
   * Protected by Cedar (Action: add_evidence).
   */
  async uploadEvidence(
    caseId: string,
    file: File,
    principalId: string = 'cit-user-1'
  ): Promise<EvidenceMetadata> {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${BASE_URL}/api/cases/${encodeURIComponent(caseId)}/evidence`, {
        method: 'POST',
        headers: {
          'X-Principal-Id': principalId,
          'X-Principal-Role': 'CITIZEN',
        },
        body: formData,
      });
      return await handleResponse<EvidenceMetadata>(res);
    } catch (err: unknown) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Evidence upload failed due to network error.', 0);
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
};

