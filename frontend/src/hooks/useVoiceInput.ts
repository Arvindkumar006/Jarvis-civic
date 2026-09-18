import { useCallback, useEffect, useRef, useState } from 'react';
import { SupportedLocale, VoiceState } from '../types/civic';

export const SUPPORTED_LOCALES: SupportedLocale[] = [
  { code: 'en-IN', name: 'English (India)', nativeName: 'English', hint: 'en' },
  { code: 'ta-IN', name: 'Tamil', nativeName: 'தமிழ்', hint: 'ta' },
  { code: 'hi-IN', name: 'Hindi', nativeName: 'हिन्दी', hint: 'hi' },
  { code: 'te-IN', name: 'Telugu', nativeName: 'తెలుగు', hint: 'te' },
  { code: 'kn-IN', name: 'Kannada', nativeName: 'ಕನ್ನಡ', hint: 'kn' },
  { code: 'bn-IN', name: 'Bengali', nativeName: 'বাংলা', hint: 'bn' },
  { code: 'mr-IN', name: 'Marathi', nativeName: 'मराठी', hint: 'mr' },
  { code: 'hinglish', name: 'Hinglish (Colloquial)', nativeName: 'Hinglish', hint: 'hinglish' },
];

// Browser SpeechRecognition interface augmentation
interface IWindowWithSpeech extends Window {
  SpeechRecognition?: any;
  webkitSpeechRecognition?: any;
}

export function useVoiceInput(onTranscriptReady?: (transcript: string) => void) {
  const [voiceState, setVoiceState] = useState<VoiceState>('IDLE');
  const [transcript, setTranscript] = useState<string>('');
  const [selectedLocale, setSelectedLocale] = useState<SupportedLocale>(SUPPORTED_LOCALES[0]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const recognitionRef = useRef<any>(null);

  // Check Web Speech API availability
  useEffect(() => {
    const win = window as unknown as IWindowWithSpeech;
    const SpeechConstructor = win.SpeechRecognition || win.webkitSpeechRecognition;

    if (!SpeechConstructor) {
      setVoiceState('UNSUPPORTED');
      return;
    }

    try {
      const recognition = new SpeechConstructor();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setVoiceState('LISTENING');
        setErrorMessage(null);
      };

      recognition.onresult = (event: any) => {
        let currentTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          currentTranscript += event.results[i][0].transcript;
        }
        setTranscript(currentTranscript);
      };

      recognition.onerror = (event: any) => {
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
          setErrorMessage('Microphone access was denied. Please allow microphone permissions.');
        } else if (event.error === 'no-speech') {
          setErrorMessage('No speech was detected. Please try speaking again.');
        } else {
          setErrorMessage(`Speech recognition error: ${event.error}`);
        }
        setVoiceState('ERROR');
      };

      recognition.onend = () => {
        setVoiceState((prev) => {
          if (prev === 'LISTENING') return 'READY';
          return prev;
        });
      };

      recognitionRef.current = recognition;
    } catch {
      setVoiceState('UNSUPPORTED');
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const startListening = useCallback(() => {
    if (!recognitionRef.current) {
      setVoiceState('UNSUPPORTED');
      return;
    }

    try {
      setTranscript('');
      const langTag = selectedLocale.code === 'hinglish' ? 'en-IN' : selectedLocale.code;
      recognitionRef.current.lang = langTag;
      recognitionRef.current.start();
      setVoiceState('LISTENING');
    } catch {
      // If already started or browser state glitch, abort and retry
      try {
        recognitionRef.current.abort();
        setTimeout(() => {
          recognitionRef.current.start();
        }, 100);
      } catch (e: any) {
        setErrorMessage('Unable to start speech recognition. ' + (e?.message || ''));
        setVoiceState('ERROR');
      }
    }
  }, [selectedLocale]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        setVoiceState('PROCESSING');
        recognitionRef.current.stop();
      } catch {
        setVoiceState('READY');
      }
    }
  }, []);

  const resetVoice = useCallback(() => {
    setVoiceState('IDLE');
    setTranscript('');
    setErrorMessage(null);
  }, []);

  const confirmTranscript = useCallback(() => {
    if (transcript.trim() && onTranscriptReady) {
      onTranscriptReady(transcript.trim());
      resetVoice();
    }
  }, [transcript, onTranscriptReady, resetVoice]);

  return {
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
    isSupported: voiceState !== 'UNSUPPORTED',
  };
}
