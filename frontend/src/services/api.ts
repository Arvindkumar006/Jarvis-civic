/**
 * Typed API Client for JARVIS Civic.
 * Communicates strictly with backend endpoints using zero-cost, local architecture.
 */

import {
  CivicCaseCreateRequest,
  CivicCaseRecord,
  ConversationRequest,
  ConversationResponse,
  EvidenceMetadata,
  PublicTrackingProjection,
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

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = 'An error occurred while communicating with JARVIS Civic.';
    try {
      const errorJson = await response.json();
      if (typeof errorJson.detail === 'string') {
        errorMessage = errorJson.detail;
      } else if (Array.isArray(errorJson.detail)) {
        errorMessage = errorJson.detail.map((e: { msg?: string }) => e.msg || 'Validation error').join(', ');
      }
    } catch {
      errorMessage = response.statusText || `Request failed with status ${response.status}`;
    }

    if (response.status === 403) {
      errorMessage = 'Authorization denied by Cedar policy enforcement.';
    } else if (response.status === 404) {
      errorMessage = 'The requested civic record could not be found.';
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
  uploadEvidence: evidenceApi.uploadEvidence,
  getPublicTracking: trackingApi.getTracking,
  checkHealth: healthApi.checkHealth,
};
