import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  User,
  RotateCcw,
  AlertCircle,
  Mic,
  MicOff,
  CornerDownLeft,
  Sparkles,
  Play,
  Pause,
  ChevronDown,
  Volume2,
  FileText,
  Paperclip,
  X,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
  HelpCircle,
} from 'lucide-react';
import { ChatMessage, EvidenceRelevanceAssessment, EvidenceRelevanceOutcome, StagedImageAttachment } from '../../types/civic';
import { SUPPORTED_LOCALES, useVoiceInput } from '../../hooks/useVoiceInput';
import { conversationApi } from '../../services/api';
import './ConversationStudio.css';

interface ConversationStudioProps {
  messages: ChatMessage[];
  isLoading?: boolean;
  isProcessing?: boolean;
  errorMessage?: string | null;
  error?: string | null;
  onSendMessage: (text: string) => void;
  onSendVoiceMessage?: (transcription: string, durationStr: string, languageName: string) => void;
  /**
   * Called when citizen sends a message with an attached image.
   * imageAssessment is the advisory Vision AI result (may be null if AI unavailable).
   */
  onSendMessageWithImage?: (
    text: string,
    imageFile: File,
    imagePreviewUrl: string,
    assessment: EvidenceRelevanceAssessment | null
  ) => void;
  onResetConversation?: () => void;
  onClearError?: () => void;
  hasCaseCreated?: boolean;
  createdCaseId?: string | null;
}

const QUICK_SIGNALS = [
  { tag: '💧 WATERLOGGING', prompt: 'There is heavy waterlogging near Anna Salai.' },
  { tag: '🛣 POTHOLE', prompt: 'There is a large pothole on the road near my area.' },
  { tag: '💡 STREETLIGHT', prompt: 'The streetlight near my street has stopped working.' },
  { tag: '🗑 GARBAGE', prompt: 'Garbage has been accumulating near my street.' },
];

export const ConversationStudio: React.FC<ConversationStudioProps> = ({
  messages,
  isLoading = false,
  isProcessing = false,
  errorMessage,
  error,
  onSendMessage,
  onSendVoiceMessage,
  onSendMessageWithImage,
  onResetConversation,
  onClearError,
  hasCaseCreated = false,
  createdCaseId = null,
}) => {
  const loading = isLoading || isProcessing;
  const activeError = error || errorMessage || null;
  const [inputText, setInputText] = useState('');
  const [isVoiceConsoleOpen, setIsVoiceConsoleOpen] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);

  /** Staged image: file + preview URL (revoked on remove/send) */
  const [stagedImage, setStagedImage] = useState<StagedImageAttachment | null>(null);
  /** Whether Vision AI call is in progress */
  const [isAssessingImage, setIsAssessingImage] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // Integrated Voice Input hook
  const {
    voiceState,
    transcript,
    setTranscript,
    selectedLocale,
    setSelectedLocale,
    errorMessage: voiceError,
    startListening,
    stopListening,
    resetVoice,
    isSupported,
  } = useVoiceInput();

  const isListening = voiceState === 'LISTENING';

  // Duration timer when recording voice
  useEffect(() => {
    let interval: any = null;
    if (isListening) {
      interval = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      setRecordingSeconds(0);
    }
    return () => clearInterval(interval);
  }, [isListening]);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading, voiceState]);

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const handleSendText = async () => {
    if (!inputText.trim() || loading) return;
    const text = inputText.trim();
    setInputText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    if (stagedImage && onSendMessageWithImage) {
      // Fire Vision AI assessment asynchronously before dispatching message
      setIsAssessingImage(true);
      let assessment: EvidenceRelevanceAssessment | null = null;
      try {
        assessment = await conversationApi.submitEvidenceRelevance(text, stagedImage.file);
      } catch {
        // Always degrade gracefully — never block the message
        assessment = null;
      } finally {
        setIsAssessingImage(false);
      }
      onSendMessageWithImage(text, stagedImage.file, stagedImage.previewUrl, assessment);
      // Revoke preview URL and clear staged image
      URL.revokeObjectURL(stagedImage.previewUrl);
      setStagedImage(null);
    } else {
      onSendMessage(text);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendText();
    }
  };

  // Toggle voice console
  const handleToggleVoiceConsole = () => {
    if (isVoiceConsoleOpen) {
      if (isListening) {
        stopListening();
      }
      setIsVoiceConsoleOpen(false);
      resetVoice();
    } else {
      setIsVoiceConsoleOpen(true);
    }
  };

  // Start voice recording
  const handleStartRecording = () => {
    startListening();
  };

  // Stop voice recording and dispatch voice message
  const handleStopAndSendVoice = () => {
    stopListening();
    const durationStr = formatDuration(recordingSeconds > 0 ? recordingSeconds : 4);
    const finalTranscript = transcript.trim();

    if (finalTranscript) {
      if (onSendVoiceMessage) {
        onSendVoiceMessage(finalTranscript, durationStr, selectedLocale.nativeName);
      } else {
        onSendMessage(finalTranscript);
      }
    }

    setIsVoiceConsoleOpen(false);
    resetVoice();
  };

  const handleCancelVoice = () => {
    if (isListening) {
      stopListening();
    }
    setIsVoiceConsoleOpen(false);
    resetVoice();
  };

  const togglePlayVoice = (msgId: string) => {
    setPlayingVoiceId((prev) => (prev === msgId ? null : msgId));
  };

  /** Handle image file selection from hidden input */
  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Revoke old preview if one existed
    if (stagedImage) URL.revokeObjectURL(stagedImage.previewUrl);
    const previewUrl = URL.createObjectURL(file);
    setStagedImage({ file, previewUrl });
    // Reset file input so re-selecting the same file triggers onChange
    e.target.value = '';
  };

  /** Remove staged image and revoke its object URL */
  const handleRemoveImage = () => {
    if (stagedImage) URL.revokeObjectURL(stagedImage.previewUrl);
    setStagedImage(null);
  };

  // Cleanup object URL on unmount
  useEffect(() => {
    return () => {
      if (stagedImage) URL.revokeObjectURL(stagedImage.previewUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="civic-conversation-studio crosshair-corner" aria-label="Citizen Intake Conversation Studio">
      {/* Studio Header Bar */}
      <div className="studio-header-bar">
        <div className="studio-brand-tag">
          <span className="studio-beacon" />
          <span className="technical-label">CIVIC INTERVIEW // ACTIVE SESSION</span>
        </div>

        <div className="studio-session-meta">
          <span className="session-status-badge">
            <span className="live-dot" /> SESSION ACTIVE
          </span>
          <span className="case-state-badge">
            {hasCaseCreated && createdCaseId ? (
              <span className="case-created-text">CASE: {createdCaseId}</span>
            ) : (
              'CASE NOT CREATED'
            )}
          </span>
          {onResetConversation && (
            <button
              type="button"
              className="btn-studio-reset"
              onClick={onResetConversation}
              title="Start a new session"
              aria-label="Reset session"
            >
              <RotateCcw size={12} />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {activeError && (
        <div className="studio-error-banner" role="alert">
          <AlertCircle size={14} />
          <span>{activeError}</span>
          {onClearError && (
            <button type="button" onClick={onClearError} className="btn-close-err" aria-label="Close error">
              ✕
            </button>
          )}
        </div>
      )}

      {/* Messages Stream (WhatsApp style: Citizen on right, JARVIS on left) */}
      <div className="studio-stream" role="log" aria-live="polite">
        {messages.length === 0 && (
          <div className="stream-onboarding-card animate-fade-in" aria-label="Civic Interview Ready">
            <div className="interview-status-tag">
              <span className="live-dot-ping" />
              <span>CIVIC INTERVIEW // READY</span>
            </div>

            <h2 className="onboarding-title-strong">TELL JARVIS WHAT NEEDS ATTENTION.</h2>
            <p className="onboarding-desc-clean">
              Speak naturally in any official language or describe the issue in plain text. JARVIS extracts civic entities, pinpoints location, and prepares an actionable municipal routing docket.
            </p>

            <div className="onboarding-input-modes">
              <button
                type="button"
                className="btn-mode-choice voice"
                onClick={() => {
                  setIsVoiceConsoleOpen(true);
                  startListening();
                }}
              >
                <Mic size={14} />
                <span>VOICE INTAKE</span>
              </button>
              <span className="mode-separator">or</span>
              <button
                type="button"
                className="btn-mode-choice text"
                onClick={() => textareaRef.current?.focus()}
              >
                <FileText size={14} />
                <span>TEXT INTAKE</span>
              </button>
            </div>

            <div className="onboarding-quick-pills">
              <span className="quick-pills-label">QUICK ISSUE SIGNALS:</span>
              <div className="pills-grid">
                {QUICK_SIGNALS.map((sig) => (
                  <button
                    key={sig.tag}
                    type="button"
                    className="onboarding-pill-btn"
                    onClick={() => onSendMessage(sig.prompt)}
                    title={`Send prompt: ${sig.prompt}`}
                  >
                    <span>{sig.tag}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`stream-turn ${msg.sender === 'citizen' ? 'turn-citizen' : 'turn-jarvis'}`}
          >
            {msg.sender === 'citizen' ? (
              msg.isVoice ? (
                /* Citizen Voice Message Bubble */
                <div className="voice-message-bubble animate-fade-in">
                  <div className="voice-bubble-header">
                    <div className="voice-badge-chip">
                      <Mic size={13} color="var(--civic-cyan)" />
                      <span>Voice message</span>
                    </div>
                    <span className="voice-duration-text">{msg.voiceDuration || '0:06'}</span>
                  </div>

                  <div className="voice-player-strip">
                    <button
                      type="button"
                      className="btn-voice-play-toggle"
                      onClick={() => togglePlayVoice(msg.id)}
                      aria-label={playingVoiceId === msg.id ? 'Pause voice message' : 'Play voice message'}
                    >
                      {playingVoiceId === msg.id ? <Pause size={13} /> : <Play size={13} />}
                    </button>
                    <div className="voice-track-scrubber">
                      <div
                        className={`scrubber-fill ${playingVoiceId === msg.id ? 'animating' : ''}`}
                        style={{ width: playingVoiceId === msg.id ? '85%' : '40%' }}
                      />
                      <div
                        className="scrubber-head"
                        style={{ left: playingVoiceId === msg.id ? '85%' : '40%' }}
                      />
                    </div>
                  </div>

                  <div className="voice-bubble-meta-row">
                    <span className="voice-locale-badge">{msg.languageHint || 'Tamil'} • Voice captured</span>
                    <span className="turn-time">
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  {msg.transcription && (
                    <div className="voice-transcription-box">
                      <span className="transcription-label">TRANSCRIPTION</span>
                      <p className="transcription-text">"{msg.transcription}"</p>
                    </div>
                  )}
                </div>
              ) : (
                              /* Citizen Plain Text Bubble — may carry an image + relevance badge */
                <div className="citizen-text-bubble animate-fade-in">
                  <div className="turn-body-text">{msg.text}</div>

                  {/* Attached Image Thumbnail */}
                  {msg.imagePreviewUrl && (
                    <div className="citizen-image-attachment">
                      <img
                        src={msg.imagePreviewUrl}
                        alt={msg.imageFilename || 'Attached image'}
                        className="attachment-thumb"
                      />
                      {msg.imageFilename && (
                        <span className="attachment-filename">{msg.imageFilename}</span>
                      )}
                    </div>
                  )}

                  {/* Vision AI Relevance Badge — advisory only */}
                  {msg.relevanceAssessment && (
                    <div
                      className={`relevance-badge relevance-${
                        msg.relevanceAssessment.relevance === EvidenceRelevanceOutcome.RELATED
                          ? 'related'
                          : msg.relevanceAssessment.relevance === EvidenceRelevanceOutcome.NOT_RELATED
                          ? 'not-related'
                          : 'uncertain'
                      }`}
                      title={msg.relevanceAssessment.reason}
                      aria-label={`Vision AI assessment: ${msg.relevanceAssessment.relevance}`}
                    >
                      {msg.relevanceAssessment.relevance === EvidenceRelevanceOutcome.RELATED ? (
                        <CheckCircle2 size={11} />
                      ) : msg.relevanceAssessment.relevance === EvidenceRelevanceOutcome.NOT_RELATED ? (
                        <XCircle size={11} />
                      ) : (
                        <HelpCircle size={11} />
                      )}
                      <span className="relevance-badge-label">
                        VISION AI · 
                        {msg.relevanceAssessment.relevance === EvidenceRelevanceOutcome.RELATED
                          ? 'RELEVANT'
                          : msg.relevanceAssessment.relevance === EvidenceRelevanceOutcome.NOT_RELATED
                          ? 'NOT RELEVANT'
                          : 'UNCERTAIN'}
                      </span>
                      {!msg.relevanceAssessment.ai_available && (
                        <span className="relevance-offline-tag">OFFLINE</span>
                      )}
                    </div>
                  )}

                  <div className="turn-meta-time">
                    <span className="turn-time">
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              )
            ) : (
              /* JARVIS Response Card */
              <div className="jarvis-reasoning-card animate-fade-in">
                <div className="turn-author-row">
                  <span className="jarvis-tag">JARVIS // CIVIC INTELLIGENCE</span>
                  <span className="turn-time">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>

                <div className="turn-body-text">{msg.text}</div>

                {/* Structured Civic Signal Breakdown if present */}
                {msg.structuredDetails && (
                  <div className="jarvis-signal-breakdown">
                    <div className="signal-breakdown-title">CIVIC SIGNAL IDENTIFIED</div>
                    <div className="signal-breakdown-grid">
                      <div className="breakdown-item">
                        <span className="bd-key">Issue</span>
                        <span className="bd-val">{msg.structuredDetails.issue || 'Pending'}</span>
                      </div>
                      <div className="breakdown-item">
                        <span className="bd-key">Location</span>
                        <span className="bd-val">{msg.structuredDetails.location || 'Pending'}</span>
                      </div>
                      <div className="breakdown-item">
                        <span className="bd-key">Department</span>
                        <span className="bd-val">{msg.structuredDetails.department || 'Pending'}</span>
                      </div>
                      <div className="breakdown-item">
                        <span className="bd-key">Urgency</span>
                        <span className="bd-val urgency-tag">{msg.structuredDetails.urgency || 'MEDIUM'}</span>
                      </div>
                    </div>
                  </div>
                )}

                {msg.followupQuestion && (
                  <div className="jarvis-followup-box">
                    <span className="followup-badge">FOLLOW-UP NEEDED</span>
                    <p className="followup-question">{msg.followupQuestion}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {(loading || isAssessingImage) && (
          <div className="stream-reasoning-indicator" aria-label="JARVIS Civic is analyzing your grievance">
            <div className="reasoning-pulse" />
            <span className="technical-label">
              {isAssessingImage ? 'VISION AI // SCANNING IMAGE...' : 'SYNTHESIZING CIVIC TELEMETRY...'}
            </span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Integrated Voice Console (when mic button clicked) */}
      {isVoiceConsoleOpen && (
        <div className="inline-voice-console animate-fade-in" role="region" aria-label="Voice Console">
          <div className="voice-console-top-bar">
            <div className="console-state-tag">
              <span className={`console-pulse-indicator ${isListening ? 'active' : ''}`} />
              <span className="technical-label">
                {isListening ? 'VOICE CONSOLE // LISTENING' : 'VOICE CONSOLE // READY'}
              </span>
            </div>

            <div className="voice-lang-select-shell">
              <select
                className="voice-lang-select"
                value={selectedLocale.code}
                onChange={(e) => {
                  const loc = SUPPORTED_LOCALES.find((l) => l.code === e.target.value);
                  if (loc) setSelectedLocale(loc);
                }}
                disabled={isListening}
                aria-label="Select spoken language"
              >
                {SUPPORTED_LOCALES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.nativeName} ({l.name})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {!isSupported ? (
            <div className="voice-console-unsupported">
              <AlertCircle size={14} color="var(--civic-amber)" />
              <span>Speech recognition not supported in this browser. Please use text input.</span>
            </div>
          ) : (
            <>
              {/* Waveform / Frequency animation */}
              <div className="voice-waveform-canvas">
                <div className={`waveform-bar ${isListening ? 'active wave-1' : ''}`} />
                <div className={`waveform-bar ${isListening ? 'active wave-2' : ''}`} />
                <div className={`waveform-bar ${isListening ? 'active wave-3' : ''}`} />
                <div className={`waveform-bar ${isListening ? 'active wave-4' : ''}`} />
                <div className={`waveform-bar ${isListening ? 'active wave-5' : ''}`} />
                <div className={`waveform-bar ${isListening ? 'active wave-3' : ''}`} />
                <div className={`waveform-bar ${isListening ? 'active wave-2' : ''}`} />
                <div className={`waveform-bar ${isListening ? 'active wave-1' : ''}`} />
                <span className="waveform-timer">{formatDuration(recordingSeconds)}</span>
              </div>

              {/* Interim Live Transcript */}
              <div className="voice-interim-box">
                <span className="interim-label">LIVE TRANSCRIPTION:</span>
                <p className="interim-text">
                  {transcript ? `"${transcript}"` : isListening ? 'Speak now... capturing your words...' : 'Tap Start Recording to speak'}
                </p>
              </div>

              {voiceError && (
                <div className="voice-error-text">
                  <AlertCircle size={12} />
                  <span>{voiceError}</span>
                </div>
              )}

              {/* Console Action Buttons */}
              <div className="voice-console-actions">
                {isListening ? (
                  <button
                    type="button"
                    className="btn-stop-record"
                    onClick={handleStopAndSendVoice}
                    aria-label="Stop recording and send"
                  >
                    <MicOff size={14} />
                    <span>STOP & SEND RECORDING</span>
                  </button>
                ) : transcript.trim() ? (
                  <>
                    <button
                      type="button"
                      className="btn-send-voice"
                      onClick={handleStopAndSendVoice}
                      aria-label="Send captured voice message"
                    >
                      <Send size={14} />
                      <span>SEND VOICE MESSAGE</span>
                    </button>
                    <button
                      type="button"
                      className="btn-start-record"
                      onClick={handleStartRecording}
                      aria-label="Re-record voice"
                    >
                      <Mic size={14} />
                      <span>RE-RECORD</span>
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="btn-start-record"
                    onClick={handleStartRecording}
                    aria-label="Start recording"
                  >
                    <Mic size={14} />
                    <span>START RECORDING</span>
                  </button>
                )}
                <button
                  type="button"
                  className="btn-cancel-record"
                  onClick={handleCancelVoice}
                  aria-label="Cancel voice input"
                >
                  CANCEL
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Unified Text Composer at Bottom */}
      <div className="studio-composer-shell">
        {/* Staged Image Preview Strip */}
        {stagedImage && (
          <div className="composer-image-preview-strip" aria-label="Staged image attachment">
            <img
              src={stagedImage.previewUrl}
              alt={stagedImage.file.name}
              className="preview-strip-thumb"
            />
            <div className="preview-strip-meta">
              <span className="preview-strip-filename">{stagedImage.file.name}</span>
              <span className="preview-strip-hint">Vision AI will assess relevance on send</span>
            </div>
            <button
              type="button"
              className="btn-preview-strip-remove"
              onClick={handleRemoveImage}
              aria-label="Remove attached image"
            >
              <X size={13} />
            </button>
          </div>
        )}

        <div className="composer-input-container">
          {/* Hidden file input for image attachment */}
          <input
            ref={imageInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            style={{ display: 'none' }}
            aria-hidden="true"
            onChange={handleImageSelect}
          />

          <textarea
            ref={textareaRef}
            className="composer-textarea"
            rows={1}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe what happened or speak naturally... (Press Enter to send, Shift+Enter for newline)"
            disabled={loading || isListening || isAssessingImage}
            aria-label="Describe what happened"
          />

          <div className="composer-actions-cluster">
            {/* Image Attach Button */}
            <button
              type="button"
              className={`btn-composer-attach ${stagedImage ? 'active' : ''}`}
              onClick={() => imageInputRef.current?.click()}
              title={stagedImage ? `Image attached: ${stagedImage.file.name}` : 'Attach image evidence'}
              aria-label="Attach image"
              disabled={loading || isAssessingImage}
            >
              <Paperclip size={15} />
            </button>

            <button
              type="button"
              className={`btn-composer-mic ${isVoiceConsoleOpen ? 'active' : ''}`}
              onClick={handleToggleVoiceConsole}
              title={isVoiceConsoleOpen ? 'Close Voice Console' : 'Open Voice Console'}
              aria-label="Voice input"
            >
              <Mic size={16} />
            </button>

            <button
              type="button"
              className="btn-composer-send"
              onClick={handleSendText}
              disabled={!inputText.trim() || loading || isListening || isAssessingImage}
              aria-label="Send message"
              title="Send message"
            >
              <span>SEND</span>
              <CornerDownLeft size={13} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
