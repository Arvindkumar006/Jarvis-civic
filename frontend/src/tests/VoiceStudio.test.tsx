import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { VoiceStudio } from '../components/VoiceStudio/VoiceStudio';

describe('VoiceStudio', () => {
  it('renders gracefully when browser does not support Web Speech API', () => {
    const handleTranscriptReady = vi.fn();

    render(<VoiceStudio onTranscriptReady={handleTranscriptReady} />);

    // Studio header
    expect(screen.getByText('AI Civic Voice Studio')).toBeInTheDocument();

    // Since jsdom doesn't have webkitSpeechRecognition, it shows UNSUPPORTED state
    expect(screen.getByText(/Speech Recognition Not Supported/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Your browser does not support the Web Speech API/i)
    ).toBeInTheDocument();
  });

  it('provides manual text fallback when speech recognition is unavailable', () => {
    const handleTranscriptReady = vi.fn();

    render(<VoiceStudio onTranscriptReady={handleTranscriptReady} />);

    const textarea = screen.getByPlaceholderText(/Speech recognition is not supported in this browser/i);
    expect(textarea).toBeInTheDocument();
  });
});
