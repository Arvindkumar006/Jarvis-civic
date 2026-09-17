import React from 'react';
import { Mic, MicOff, Send, X, AlertCircle } from 'lucide-react';
import { SUPPORTED_LOCALES, useVoiceInput } from '../../hooks/useVoiceInput';
import './VoiceStudio.css';

interface VoiceStudioProps {
  onSendMessage?: (text: string, languageHint?: string) => void;
  onTranscriptReady?: (text: string) => void;
  disabled?: boolean;
}

export const VoiceStudio: React.FC<VoiceStudioProps> = ({
  onSendMessage,
  onTranscriptReady,
  disabled = false,
}) => {
  const handleOutput = (finalText: string) => {
    if (onSendMessage) onSendMessage(finalText, selectedLocale.hint);
    if (onTranscriptReady) onTranscriptReady(finalText);
  };

  const {
    voiceState,
    transcript,
    setTranscript,
    selectedLocale,
    setSelectedLocale,
    errorMessage,
    startListening,
    stopListening,
    resetVoice,
    confirmTranscript,
    isSupported,
  } = useVoiceInput((finalText) => {
    handleOutput(finalText);
  });

  const isListening = voiceState === 'LISTENING';

  const handleToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  const handleManualSend = () => {
    if (transcript.trim()) {
      confirmTranscript();
    }
  };

  return (
    <div
      className={`voice-console crosshair-corner ${isListening ? 'state-listening' : ''}`}
      aria-label="Civic Voice Console"
    >
      {/* Console Header Bar */}
      <div className="voice-console-bar">
        <div className="voice-channel-tag">
          <span className="channel-indicator" />
          <span className="channel-text">AI Civic Voice Studio</span>
          <span className="channel-subtext" style={{ color: 'var(--text-muted)', marginLeft: '6px', fontSize: '0.7rem' }}>
            // {selectedLocale.code}
          </span>
        </div>

        <div className="voice-locale-dropdown-wrap">
          <label htmlFor="voice-locale-select" className="sr-only">
            Select Language
          </label>
          <select
            id="voice-locale-select"
            className="voice-locale-select"
            value={selectedLocale.code}
            onChange={(e) => {
              const found = SUPPORTED_LOCALES.find((l) => l.code === e.target.value);
              if (found) setSelectedLocale(found);
            }}
            disabled={isListening || disabled}
          >
            {SUPPORTED_LOCALES.map((loc) => (
              <option key={loc.code} value={loc.code}>
                {loc.nativeName} ({loc.name})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Unsupported Warning */}
      {!isSupported && (
        <div className="voice-alert-strip" role="alert">
          <AlertCircle size={14} />
          <span>Speech Recognition Not Supported in this browser. Your browser does not support the Web Speech API. Text input is fully active.</span>
        </div>
      )}

      {errorMessage && (
        <div className="voice-alert-strip error" role="alert">
          <AlertCircle size={14} />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Center Console Stage */}
      <div className="voice-stage">
        <div className="voice-state-pill">
          <span className={`pill-beacon ${isListening ? 'active' : ''}`} />
          <span className="pill-title">
            {isListening
              ? 'LISTENING'
              : voiceState === 'PROCESSING'
              ? 'UNDERSTANDING YOUR REPORT...'
              : voiceState === 'READY'
              ? 'STATEMENT CAPTURED'
              : !isSupported
              ? 'STANDBY • TEXT FALLBACK'
              : 'STANDBY'}
          </span>
        </div>

        {/* Technical Waveform Line */}
        <div className={`technical-waveform ${isListening ? 'active' : ''}`} aria-hidden="true">
          <span className="wave-bar b1" />
          <span className="wave-bar b2" />
          <span className="wave-bar b3" />
          <span className="wave-bar b4" />
          <span className="wave-bar b5" />
          <span className="wave-bar b6" />
          <span className="wave-bar b7" />
          <span className="wave-bar b8" />
          <span className="wave-bar b9" />
        </div>

        <p className="voice-instruction">
          {isListening
            ? `Speaking in ${selectedLocale.nativeName} • State your grievance naturally`
            : !isSupported
            ? 'Type your civic grievance below'
            : 'Tap the console microphone to speak'}
        </p>

        {/* Console Microphone Trigger */}
        <div className="voice-trigger-row">
          <button
            type="button"
            className={`btn-console-mic ${isListening ? 'listening' : ''}`}
            onClick={handleToggle}
            disabled={!isSupported || disabled}
            aria-label={isListening ? 'Stop listening' : 'Start speaking with JARVIS Civic'}
            title={isListening ? 'Stop recording' : 'Tap to speak'}
          >
            {isListening ? <MicOff size={22} /> : <Mic size={22} />}
          </button>
        </div>
      </div>

      {/* Editable Civic Statement / Fallback Input */}
      {(!isSupported || transcript) && (
        <div className="voice-statement-box">
          <div className="statement-header">
            <span className="technical-label">
              {!isSupported ? 'DIRECT TEXT FALLBACK' : 'TRANSCRIBED CIVIC STATEMENT (EDITABLE)'}
            </span>
            {transcript && (
              <button
                type="button"
                className="btn-clear-transcript"
                onClick={resetVoice}
                title="Discard transcript"
              >
                <X size={12} /> Clear
              </button>
            )}
          </div>
          <textarea
            className="statement-textarea"
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder={
              !isSupported
                ? 'Speech recognition is not supported in this browser. Type your grievance here...'
                : 'Review and edit your spoken civic statement...'
            }
            rows={2}
          />
          {transcript.trim() && (
            <div className="statement-actions">
              <button
                type="button"
                className="btn-submit-statement"
                onClick={handleManualSend}
              >
                <Send size={13} />
                <span>Submit Statement to JARVIS</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
