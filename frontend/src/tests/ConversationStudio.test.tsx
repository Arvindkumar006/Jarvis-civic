/**
 * Frontend tests for Phase 8.9: Citizen Evidence Vision AI Relevance Pipeline.
 *
 * Tests:
 * 1. Paperclip button is rendered in the composer.
 * 2. Attaching an image shows the preview strip with filename and hint.
 * 3. Removing the staged image hides the preview strip.
 * 4. Sending with an image calls onSendMessageWithImage (not onSendMessage).
 * 5. Sending without an image calls onSendMessage (not onSendMessageWithImage).
 * 6. RELATED assessment badge renders correctly.
 * 7. NOT_RELATED assessment badge renders correctly and does NOT block message dispatch.
 * 8. UNCERTAIN assessment badge renders correctly.
 * 9. ai_available=false shows OFFLINE tag.
 * 10. Vision AI call failure degrades gracefully (assessment=null, message still dispatched).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { ConversationStudio } from '../components/Conversation/ConversationStudio';
import * as api from '../services/api';
import {
  ChatMessage,
  EvidenceRelevanceOutcome,
  EvidenceRelevanceAssessment,
} from '../types/civic';

// ---- Mocks ---------------------------------------------------------------

vi.mock('../services/api', () => ({
  conversationApi: {
    intake: vi.fn(),
    submitEvidenceRelevance: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    statusCode?: number;
    constructor(message: string, statusCode?: number) {
      super(message);
      this.statusCode = statusCode;
    }
  },
  onUnauthorized: vi.fn(() => () => {}),
  notifyUnauthorized: vi.fn(),
}));

vi.mock('../hooks/useVoiceInput', () => ({
  SUPPORTED_LOCALES: [{ code: 'en-IN', name: 'English (India)', nativeName: 'English', hint: '' }],
  useVoiceInput: () => ({
    voiceState: 'IDLE',
    transcript: '',
    setTranscript: vi.fn(),
    selectedLocale: { code: 'en-IN', name: 'English', nativeName: 'English', hint: '' },
    setSelectedLocale: vi.fn(),
    errorMessage: null,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    resetVoice: vi.fn(),
    isSupported: true,
  }),
}));

// ---- Helpers -------------------------------------------------------------

const makeMessage = (overrides: Partial<ChatMessage> = {}): ChatMessage => ({
  id: 'msg-001',
  sender: 'citizen',
  text: 'Test message',
  timestamp: new Date().toISOString(),
  ...overrides,
});

const RELATED_ASSESSMENT: EvidenceRelevanceAssessment = {
  relevance: EvidenceRelevanceOutcome.RELATED,
  reason: 'Road damage visible',
  detected_features: ['pothole'],
  confidence: 0.92,
  model_id: 'llama3.2-vision',
  ai_available: true,
};

const NOT_RELATED_ASSESSMENT: EvidenceRelevanceAssessment = {
  relevance: EvidenceRelevanceOutcome.NOT_RELATED,
  reason: 'Photo of a cat, unrelated',
  detected_features: ['cat'],
  confidence: 0.88,
  model_id: 'llama3.2-vision',
  ai_available: true,
};

const UNCERTAIN_ASSESSMENT: EvidenceRelevanceAssessment = {
  relevance: EvidenceRelevanceOutcome.UNCERTAIN,
  reason: 'Image too blurry to assess',
  detected_features: [],
  confidence: 0.3,
  model_id: 'llama3.2-vision',
  ai_available: true,
};

const OFFLINE_ASSESSMENT: EvidenceRelevanceAssessment = {
  relevance: EvidenceRelevanceOutcome.UNCERTAIN,
  reason: 'Vision AI offline or unavailable.',
  detected_features: [],
  confidence: null,
  model_id: null,
  ai_available: false,
};

const onSendMessage = vi.fn();
const defaultProps = {
  messages: [] as ChatMessage[],
  isLoading: false,
  onSendMessage,
};

function renderStudio(props: Record<string, unknown> = {}) {
  return render(<ConversationStudio {...defaultProps} {...props} />);
}

// ---- Tests ----------------------------------------------------------------

describe('ConversationStudio — Phase 8.9 Image Attachment & Vision AI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.conversationApi.submitEvidenceRelevance).mockResolvedValue(RELATED_ASSESSMENT);
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock-url');
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('1: renders paperclip attach button in composer', () => {
    renderStudio();
    expect(screen.getByRole('button', { name: /attach image/i })).toBeTruthy();
  });

  it('2: attaching an image shows preview strip with filename and vision hint', async () => {
    renderStudio();
    const file = new File([new Uint8Array(100)], 'pothole.jpg', { type: 'image/jpeg' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).toBeTruthy();

    await act(async () => {
      Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
      fireEvent.change(fileInput);
    });

    expect(screen.getByText('pothole.jpg')).toBeTruthy();
    expect(screen.getByText(/vision ai will assess relevance/i)).toBeTruthy();
  });

  it('3: removing staged image hides the preview strip', async () => {
    renderStudio();
    const file = new File([new Uint8Array(100)], 'evidence.png', { type: 'image/png' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
      fireEvent.change(fileInput);
    });

    expect(screen.getByText('evidence.png')).toBeTruthy();

    const removeBtn = screen.getByRole('button', { name: /remove attached image/i });
    await act(async () => { fireEvent.click(removeBtn); });

    expect(screen.queryByText('evidence.png')).toBeNull();
  });

  it('4: sending with staged image calls onSendMessageWithImage', async () => {
    const onSendMessageWithImage = vi.fn();
    renderStudio({ onSendMessageWithImage });

    const file = new File([new Uint8Array(100)], 'road.jpg', { type: 'image/jpeg' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
      fireEvent.change(fileInput);
    });

    const textarea = screen.getByRole('textbox', { name: /describe what happened/i });
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'Pothole on road' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));
    });

    await waitFor(() => {
      expect(onSendMessageWithImage).toHaveBeenCalledOnce();
      const [text, imageFile, previewUrl, assessment] = onSendMessageWithImage.mock.calls[0];
      expect(text).toBe('Pothole on road');
      expect(imageFile).toBe(file);
      expect(typeof previewUrl).toBe('string');
      expect(assessment).toEqual(RELATED_ASSESSMENT);
    });

    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it('5: sending without image calls onSendMessage', async () => {
    renderStudio();

    const textarea = screen.getByRole('textbox', { name: /describe what happened/i });
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'Waterlogging near station' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));
    });

    expect(onSendMessage).toHaveBeenCalledWith('Waterlogging near station');
    expect(api.conversationApi.submitEvidenceRelevance).not.toHaveBeenCalled();
  });

  it('6: RELATED assessment badge renders with RELEVANT label', () => {
    const msg = makeMessage({ relevanceAssessment: RELATED_ASSESSMENT });
    renderStudio({ messages: [msg] });
    const badgeEl = document.querySelector('[aria-label="Vision AI assessment: RELATED"]');
    expect(badgeEl).toBeTruthy();
    expect(badgeEl?.textContent).toMatch(/RELEVANT/i);
  });

  it('7: NOT_RELATED badge renders correctly', () => {
    const msg = makeMessage({ relevanceAssessment: NOT_RELATED_ASSESSMENT });
    renderStudio({ messages: [msg] });
    const badgeEl = document.querySelector('[aria-label="Vision AI assessment: NOT_RELATED"]');
    expect(badgeEl).toBeTruthy();
    expect(badgeEl?.textContent).toMatch(/NOT RELEVANT/i);
  });

  it('8: UNCERTAIN assessment badge renders correctly', () => {
    const msg = makeMessage({ relevanceAssessment: UNCERTAIN_ASSESSMENT });
    renderStudio({ messages: [msg] });
    const badgeEl = document.querySelector('[aria-label="Vision AI assessment: UNCERTAIN"]');
    expect(badgeEl).toBeTruthy();
    expect(badgeEl?.textContent).toMatch(/UNCERTAIN/i);
  });

  it('9: OFFLINE tag appears when ai_available is false', () => {
    const msg = makeMessage({ relevanceAssessment: OFFLINE_ASSESSMENT });
    renderStudio({ messages: [msg] });
    expect(screen.getByText('OFFLINE')).toBeTruthy();
  });

  it('10: Vision AI failure degrades gracefully; message dispatched with null assessment', async () => {
    const onSendMessageWithImage = vi.fn();
    vi.mocked(api.conversationApi.submitEvidenceRelevance).mockRejectedValue(
      new Error('Network error')
    );
    renderStudio({ onSendMessageWithImage });

    const file = new File([new Uint8Array(100)], 'flood.jpg', { type: 'image/jpeg' });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

    await act(async () => {
      Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
      fireEvent.change(fileInput);
    });

    const textarea = screen.getByRole('textbox', { name: /describe what happened/i });
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'Flooding on main road' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));
    });

    await waitFor(() => {
      expect(onSendMessageWithImage).toHaveBeenCalledOnce();
      const [text, , , assessment] = onSendMessageWithImage.mock.calls[0];
      expect(text).toBe('Flooding on main road');
      expect(assessment).toBeNull();
    });
  });
});

