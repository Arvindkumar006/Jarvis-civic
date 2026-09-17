import React, { useState } from 'react';
import { Mic, ArrowRight, CornerDownLeft, Sparkles } from 'lucide-react';
import './IntakeHero.css';

interface IssueSignal {
  tag: string;
  label: string;
  detail: string;
  prompt: string;
}

const ISSUE_SIGNALS: IssueSignal[] = [
  {
    tag: 'WATER',
    label: 'Waterlogging',
    detail: 'Anna Salai metro corridor flooding',
    prompt: 'Severe waterlogging at Anna Salai near Thousand Lights metro station blocking the entire left lane.',
  },
  {
    tag: 'ROADS',
    label: 'Road Hazard',
    detail: 'Deep pothole causing vehicle accidents',
    prompt: 'Dangerous deep pothole on MG Road near the railway overbridge causing two-wheeler accidents.',
  },
  {
    tag: 'LIGHT',
    label: 'Streetlight',
    detail: 'Consecutive night blackout on Sector 4',
    prompt: 'All streetlights are completely out for three consecutive nights on 5th Main Road, Sector 4.',
  },
  {
    tag: 'WASTE',
    label: 'Garbage Dump',
    detail: 'Pedestrian walkway overflow',
    prompt: 'Commercial garbage accumulation spreading into the pedestrian walkway near the daily vegetable market.',
  },
];

interface IntakeHeroProps {
  onSelectPrompt: (promptText: string) => void;
  voiceActive: boolean;
  onToggleVoice: () => void;
}

export const IntakeHero: React.FC<IntakeHeroProps> = ({
  onSelectPrompt,
  voiceActive,
  onToggleVoice,
}) => {
  const [intakeMode, setIntakeMode] = useState<'speak' | 'type'>('speak');
  const [typedInput, setTypedInput] = useState('');

  const handleTypeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (typedInput.trim()) {
      onSelectPrompt(typedInput.trim());
      setTypedInput('');
    }
  };

  return (
    <section className="civic-hero-intake" aria-label="Civic Intake Console">
      {/* Editorial Title Block */}
      <div className="hero-editorial">
        <div className="hero-ruler-tag">
          <span className="ruler-line" />
          <span className="ruler-text">CIVIC INTELLIGENCE INTERFACE // INTAKE SYSTEM</span>
          <span className="ruler-line" />
        </div>

        <h1 className="hero-headline">
          Tell us what <br />
          <span className="hero-headline-dim">needs attention.</span>
        </h1>

        <div className="hero-subline">
          <span className="hero-accent-phrase">JARVIS understands the rest.</span>
          <p className="hero-copy">
            Describe a civic problem naturally. JARVIS turns your words into a structured, actionable civic record.
          </p>
        </div>
      </div>

      {/* Central Interactive Console */}
      <div className="hero-central-console crosshair-corner">
        <div className="console-mode-selector" role="tablist" aria-label="Input Mode Selector">
          <button
            type="button"
            className={`mode-btn ${intakeMode === 'speak' ? 'active' : ''}`}
            onClick={() => {
              setIntakeMode('speak');
              if (!voiceActive) onToggleVoice();
            }}
            role="tab"
            aria-selected={intakeMode === 'speak'}
          >
            <Mic size={14} />
            <span>Speak</span>
          </button>
          <button
            type="button"
            className={`mode-btn ${intakeMode === 'type' ? 'active' : ''}`}
            onClick={() => {
              setIntakeMode('type');
              if (voiceActive) onToggleVoice();
            }}
            role="tab"
            aria-selected={intakeMode === 'type'}
          >
            <span>Type</span>
          </button>
        </div>

        {/* Speak Primary Surface */}
        {intakeMode === 'speak' && (
          <div className="console-speak-stage">
            <div className="voice-orb-container">
              <div className={`voice-radar-ring ${voiceActive ? 'pulsing' : ''}`} />
              <button
                type="button"
                className={`voice-orb-btn ${voiceActive ? 'active' : ''}`}
                onClick={onToggleVoice}
                aria-label={voiceActive ? 'Deactivate Voice Console' : 'Activate Voice Console'}
                title="Tap to speak your civic issue"
              >
                <Mic size={26} className="orb-mic-icon" />
              </button>
            </div>
            <div className="speak-status-text">
              {voiceActive ? 'VOICE CONSOLE ACTIVE — SPEAK NATURALLY' : 'TAP TO START SPEAKING'}
            </div>
            <div className="speak-locale-hint">
              Supports 7 Indian languages • English, Tamil, Hindi, Telugu, Kannada, Bengali, Marathi
            </div>
          </div>
        )}

        {/* Type Primary Surface */}
        {intakeMode === 'type' && (
          <form className="console-type-stage" onSubmit={handleTypeSubmit}>
            <div className="type-input-wrap">
              <input
                type="text"
                className="hero-type-input"
                placeholder="Describe municipal defect (e.g. Broken water pipeline at 4th Cross Road)..."
                value={typedInput}
                onChange={(e) => setTypedInput(e.target.value)}
                autoFocus
              />
              <button
                type="submit"
                className="btn-type-submit"
                disabled={!typedInput.trim()}
                aria-label="Send to JARVIS"
              >
                <CornerDownLeft size={16} />
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Compact Issue Signals */}
      <div className="issue-signals-wrapper">
        <div className="issue-signals-label">
          <span>QUICK ISSUE SIGNALS</span>
        </div>
        <div className="issue-signals-grid">
          {ISSUE_SIGNALS.map((signal) => (
            <button
              key={signal.tag}
              type="button"
              className="signal-chip"
              onClick={() => onSelectPrompt(signal.prompt)}
              title={`Load ${signal.label} signal`}
            >
              <div className="signal-chip-top">
                <span className="signal-tag">{signal.tag}</span>
                <span className="signal-title">{signal.label}</span>
              </div>
              <div className="signal-detail">{signal.detail}</div>
              <div className="signal-arrow">
                <ArrowRight size={12} />
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
};
