import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Navbar, ActiveTab } from './components/Layout/Navbar';
import { ProductExperience } from './components/Experience/ProductExperience';
import { ConversationStudio } from './components/Conversation/ConversationStudio';
import { ExtractionHUD } from './components/HUD/ExtractionHUD';
import { VoiceStudio } from './components/VoiceStudio/VoiceStudio';
import { ActionDocketModal } from './components/Docket/ActionDocketModal';
import { EvidenceStudio } from './components/Evidence/EvidenceStudio';
import { TrackingView } from './components/Tracking/TrackingView';
import { AuthorityConsole } from './components/Authority/AuthorityConsole';
import { CivicMap } from './components/Map/CivicMap';
import {
  CanonicalCivicState,
  ChatMessage,
  CivicCaseCreateRequest,
  CivicCaseRecord,
  ApplicationRole,
} from './types/civic';
import { conversationApi, casesApi, healthApi } from './services/api';
import { WorkspaceProvider, useWorkspace } from './context/WorkspaceContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginModal } from './components/Auth/LoginModal';
import { CheckCircle2, Search, Paperclip, Mic, ArrowRight, MapPin, Sparkles } from 'lucide-react';
import './App.css';

const LOCAL_STORAGE_DOCKETS_KEY = 'jarvis_civic_recent_dockets';

interface QuickPromptSignal {
  tag: string;
  label: string;
  prompt: string;
}

const COMPACT_ISSUE_SIGNALS: QuickPromptSignal[] = [
  {
    tag: 'WATER',
    label: 'Waterlogging',
    prompt: 'Severe waterlogging at Anna Salai near Thousand Lights metro station blocking the entire left lane.',
  },
  {
    tag: 'ROADS',
    label: 'Pothole',
    prompt: 'Dangerous deep pothole on MG Road near the railway overbridge causing two-wheeler accidents.',
  },
  {
    tag: 'LIGHT',
    label: 'Streetlight',
    prompt: 'All streetlights are completely out for three consecutive nights on 5th Main Road, Sector 4.',
  },
  {
    tag: 'WASTE',
    label: 'Garbage',
    prompt: 'Commercial garbage accumulation spreading into the pedestrian walkway near the daily vegetable market.',
  },
];

const AppContent: React.FC = () => {
  const { session } = useWorkspace();

  let auth: ReturnType<typeof useAuth> | null = null;
  try {
    auth = useAuth();
  } catch {
    auth = null;
  }

  const isAuthenticated = auth ? auth.isAuthenticated : session.role !== ApplicationRole.PUBLIC;
  const role = auth && auth.isAuthenticated ? auth.role : session.role;
  const isLoading = auth ? auth.isLoading : false;

  // Navigation & View state (Adaptive default based on role)
  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    if (!isAuthenticated) return 'experience';
    if (role === ApplicationRole.PUBLIC) return 'track';
    if (
      role === ApplicationRole.AUTHORITY_OFFICER ||
      role === ApplicationRole.MUNICIPAL_SUPERVISOR ||
      role === ApplicationRole.ADMINISTRATOR
    ) {
      return 'console';
    }
    return 'report';
  });

  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  const prevAuthRoleRef = useRef<string | null>(null);

  // Synchronize and guard tab when authentication or role changes
  useEffect(() => {
    if (isLoading) return;

    const currentKey = isAuthenticated ? `${role}` : 'unauth';
    const roleChanged = prevAuthRoleRef.current !== currentKey;
    prevAuthRoleRef.current = currentKey;

    if (!isAuthenticated) {
      if (roleChanged || (activeTab !== 'experience' && activeTab !== 'track')) {
        setActiveTab('experience');
      }
      return;
    }

    if (roleChanged) {
      if (role === ApplicationRole.PUBLIC) {
        setActiveTab('track');
      } else if (
        role === ApplicationRole.AUTHORITY_OFFICER ||
        role === ApplicationRole.MUNICIPAL_SUPERVISOR ||
        role === ApplicationRole.ADMINISTRATOR
      ) {
        setActiveTab('console');
      } else if (role === ApplicationRole.CITIZEN) {
        setActiveTab('report');
      }
    } else {
      // Guard forbidden tabs if already settled
      if (role === ApplicationRole.CITIZEN && (activeTab === 'console' || activeTab === 'audit')) {
        setActiveTab('report');
      } else if (
        (role === ApplicationRole.AUTHORITY_OFFICER ||
          role === ApplicationRole.MUNICIPAL_SUPERVISOR ||
          role === ApplicationRole.ADMINISTRATOR) &&
        activeTab === 'report'
      ) {
        setActiveTab('console');
      }
    }
  }, [isLoading, isAuthenticated, role, activeTab]);

  const handleSelectTab = (tab: ActiveTab) => {
    if (!isAuthenticated && tab !== 'experience' && tab !== 'track') {
      if (auth) {
        auth.openLogin();
      }
      return;
    }
    setActiveTab(tab);
  };

  // Session & Conversation state
  const [sessionId] = useState<string>(
    () => `session-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [canonicalState, setCanonicalState] = useState<CanonicalCivicState | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  // Voice Console state
  const [voiceOpen, setVoiceOpen] = useState(false);

  // Location / Map Confirmation state
  const [confirmedLocation, setConfirmedLocation] = useState<string | null>(null);
  const [selectedCoordinates, setSelectedCoordinates] = useState<{
    lat: number;
    lng: number;
    source: 'MAP_SELECTED';
  } | null>(null);

  // Docket modal & Case creation state
  const [isDocketModalOpen, setIsDocketModalOpen] = useState(false);
  const [createdCase, setCreatedCase] = useState<CivicCaseRecord | null>(null);
  const [selectedCaseForEvidence, setSelectedCaseForEvidence] = useState<string>('');
  const [selectedCaseForTracking, setSelectedCaseForTracking] = useState<string>('');

  // Persisted recent dockets
  const [recentDockets, setRecentDockets] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_DOCKETS_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // Check backend health periodically
  useEffect(() => {
    let mounted = true;
    const check = async () => {
      const ok = await healthApi.checkHealth();
      if (mounted) setBackendOnline(ok);
    };
    check();
    const timer = setInterval(check, 15000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  // Save dockets to local storage
  const saveDocketId = useCallback((caseId: string) => {
    setRecentDockets((prev) => {
      const updated = [caseId, ...prev.filter((id) => id !== caseId)].slice(0, 10);
      try {
        localStorage.setItem(LOCAL_STORAGE_DOCKETS_KEY, JSON.stringify(updated));
      } catch {
        // ignore local storage errors
      }
      return updated;
    });
  }, []);

  // Core text conversation submission handler
  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isProcessing) return;

    const citizenMsg: ChatMessage = {
      id: `msg-${Date.now()}-c`,
      sender: 'citizen',
      text: text.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, citizenMsg]);
    setIsProcessing(true);
    setChatError(null);

    try {
      const response = await conversationApi.intake({
        message: text.trim(),
        session_id: sessionId,
      });

      setCanonicalState(response.state);

      const replyText =
        (response as any).reply ||
        response.state?.followup_question ||
        (response.state?.missing_fields && response.state.missing_fields.length > 0
          ? `I have recorded your report. Could you please provide the ${response.state.missing_fields[0]} to finalize the docket?`
          : 'Your grievance has been analyzed and classified. Ready to generate the Civic Action Docket.');

      const jarvisMsg: ChatMessage = {
        id: `msg-${Date.now()}-j`,
        sender: 'jarvis',
        text: replyText,
        timestamp: new Date().toISOString(),
        missingFields: response.state.missing_fields,
        followupQuestion: response.state.followup_question,
        readyForAction: response.state.ready_for_action,
        structuredDetails:
          response.state && (response.state.intent || response.state.location)
            ? {
                issue: response.state.intent?.replace(/_/g, ' ') || 'Pending analysis',
                location: response.state.location || 'Awaiting location',
                department: response.state.department?.replace(/_/g, ' ') || 'Pending routing',
                urgency: response.state.urgency || 'MEDIUM',
              }
            : undefined,
      };
      setMessages((prev) => [...prev, jarvisMsg]);
    } catch (err: any) {
      setChatError(err.message || 'Error communicating with civic reasoning agent.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Voice message handler (WhatsApp style)
  const handleSendVoiceMessage = async (
    transcriptText: string,
    durationStr: string,
    langName: string
  ) => {
    if (!transcriptText.trim() || isProcessing) return;

    const citizenVoiceMsg: ChatMessage = {
      id: `msg-${Date.now()}-cv`,
      sender: 'citizen',
      text: transcriptText.trim(),
      timestamp: new Date().toISOString(),
      isVoice: true,
      voiceDuration: durationStr,
      languageHint: langName,
      transcription: transcriptText.trim(),
    };

    setMessages((prev) => [...prev, citizenVoiceMsg]);
    setIsProcessing(true);
    setChatError(null);

    try {
      const response = await conversationApi.intake({
        message: transcriptText.trim(),
        session_id: sessionId,
      });

      setCanonicalState(response.state);

      const replyText =
        (response as any).reply ||
        response.state?.followup_question ||
        (response.state?.missing_fields && response.state.missing_fields.length > 0
          ? `I have recorded your voice grievance. Could you please specify the ${response.state.missing_fields[0]}?`
          : 'Your voice grievance has been analyzed and classified. Ready to generate the Civic Action Docket.');

      const jarvisMsg: ChatMessage = {
        id: `msg-${Date.now()}-j`,
        sender: 'jarvis',
        text: replyText,
        timestamp: new Date().toISOString(),
        missingFields: response.state.missing_fields,
        followupQuestion: response.state.followup_question,
        readyForAction: response.state.ready_for_action,
        structuredDetails:
          response.state && (response.state.intent || response.state.location)
            ? {
                issue: response.state.intent?.replace(/_/g, ' ') || 'Pending analysis',
                location: response.state.location || 'Awaiting location',
                department: response.state.department?.replace(/_/g, ' ') || 'Pending routing',
                urgency: response.state.urgency || 'MEDIUM',
              }
            : undefined,
      };
      setMessages((prev) => [...prev, jarvisMsg]);
    } catch (err: any) {
      setChatError(err.message || 'Error communicating with civic reasoning agent.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Reset conversation session
  const handleResetConversation = () => {
    setMessages([]);
    setCanonicalState(null);
    setChatError(null);
    setCreatedCase(null);
    setConfirmedLocation(null);
    setSelectedCoordinates(null);
  };

  // Create Case Docket handler
  const handleCreateCase = async (payload: CivicCaseCreateRequest) => {
    const fullPayload: CivicCaseCreateRequest = {
      description: payload.description,
      location: confirmedLocation || payload.location,
      department: payload.department,
      pincode: payload.pincode,
      is_public: true,
      latitude: payload.latitude ?? selectedCoordinates?.lat ?? null,
      longitude: payload.longitude ?? selectedCoordinates?.lng ?? null,
      location_source:
        payload.location_source ??
        selectedCoordinates?.source ??
        (payload.location ? 'TEXT_REFERENCE' : 'UNCONFIRMED'),
    };

    const newCase = await casesApi.createCase(fullPayload, session.principalId);
    setCreatedCase(newCase);
    saveDocketId(newCase.case_id);
    setIsDocketModalOpen(false);
  };

  // Switch to Evidence Studio with specific case
  const handleSelectCaseForEvidence = (caseId: string) => {
    setSelectedCaseForEvidence(caseId);
    setActiveTab('evidence');
  };

  // Switch to Tracking View with specific case
  const handleSelectCaseForTracking = (caseId: string) => {
    setSelectedCaseForTracking(caseId);
    setActiveTab('track');
  };

  if (isLoading) {
    return (
      <div className="app-bootstrap-loader" role="status" aria-label="Initializing security context">
        <div className="bootstrap-loader-box crosshair-corner">
          <div className="bootstrap-spinner" />
          <div className="bootstrap-meta">
            <span className="technical-label">JARVIS CIVIC // AUTHENTICATING CONTEXT</span>
            <h2 className="bootstrap-title">Verifying Security Session</h2>
            <p className="bootstrap-sub">Querying backend session authority via GET /api/auth/me...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Navbar
        activeTab={activeTab}
        onSelectTab={handleSelectTab}
        backendOnline={backendOnline}
        docketCount={recentDockets.length}
      />

      <main className="main-viewport">
        {/* PAGE 01: PRODUCT EXPERIENCE */}
        {activeTab === 'experience' && (
          <ProductExperience
            onStartReport={() => setActiveTab('report')}
            onExploreTrack={() => setActiveTab('track')}
            onNavigateToConsole={() => setActiveTab('console')}
            onNavigateToAudit={() => setActiveTab('audit')}
          />
        )}

        {/* AUTHORITY / SUPERVISOR / ADMIN CONSOLE */}
        {activeTab === 'console' && (
          <div className="authority-console-container">
            <AuthorityConsole
              onNavigateToTrack={(caseId) => {
                if (caseId) setSelectedCaseForTracking(caseId);
                setActiveTab('track');
              }}
              onNavigateToEvidence={(caseId) => {
                if (caseId) setSelectedCaseForEvidence(caseId);
                setActiveTab('evidence');
              }}
              onNavigateToAudit={(caseId) => {
                if (caseId) setSelectedCaseForTracking(caseId);
                setActiveTab('audit');
              }}
              recentCaseIds={recentDockets}
            />
          </div>
        )}

        {/* CITIZEN REPORT / CIVIC INTELLIGENCE STUDIO */}
        {activeTab === 'report' && (
          <div className="report-tab-container">
            {/* Top Civic Intelligence Intake Banner */}
            <div className="report-intake-header">
              <div className="intake-prehead">
                <span className="technical-label">CIVIC INTELLIGENCE INTERFACE // LIVE INTAKE</span>
              </div>
              <h1 className="intake-headline">Tell us what needs attention.</h1>
              <p className="intake-subheading">
                Speak naturally or type what you see. JARVIS transforms civic words into structured civic actions.
              </p>

              {/* Quick Municipal Scenario Triggers */}
              <div className="intake-toolbar-row">
                <div className="quick-signals-strip">
                  <span className="quick-signals-label">QUICK SIGNALS:</span>
                  <div className="signals-btn-group">
                    {COMPACT_ISSUE_SIGNALS.map((sig) => (
                      <button
                        key={sig.tag}
                        type="button"
                        className="quick-signal-btn"
                        onClick={() => handleSendMessage(sig.prompt)}
                        title={`Trigger ${sig.label} defect prompt`}
                      >
                        <span className="sig-tag">{sig.tag}</span>
                        <span className="sig-title">{sig.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Case Creation Success Banner */}
            {createdCase && (
              <div className="case-created-banner crosshair-corner" role="status">
                <div className="case-banner-icon">
                  <CheckCircle2 size={20} color="var(--civic-emerald)" />
                </div>
                <div className="case-banner-body">
                  <div className="case-banner-title">
                    CIVIC ACTION DOCKET CREATED // CASE ID GENERATED
                  </div>
                  <div className="case-banner-meta">
                    DOCKET ID: <span className="case-id-code">{createdCase.case_id}</span> • ROUTED TO:{' '}
                    <strong>{createdCase.department.replace(/_/g, ' ')}</strong>
                  </div>
                  <div className="case-banner-actions">
                    <button
                      type="button"
                      className="btn-banner-action"
                      onClick={() => handleSelectCaseForTracking(createdCase.case_id)}
                    >
                      <Search size={13} />
                      <span>Track Journey</span>
                    </button>
                    <button
                      type="button"
                      className="btn-banner-action"
                      onClick={() => handleSelectCaseForEvidence(createdCase.case_id)}
                    >
                      <Paperclip size={13} />
                      <span>Attach Evidence</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Active Session Connector Line */}
            <div
              className={`workspace-session-flow ${
                isProcessing
                  ? 'state-analyzing'
                  : canonicalState?.ready_for_action
                  ? 'state-validated'
                  : 'state-idle'
              }`}
              aria-label="Session flow connectivity"
            >
              <div className="flow-stage-node left">
                <span className="node-marker" />
                <span className="stage-tag">CONVERSATION</span>
              </div>
              <div className="flow-spine-connector">
                <span className="flow-pulse-beam" />
              </div>
              <div className="flow-stage-node center">
                <span className="node-marker" />
                <span className="stage-tag">EXTRACTION</span>
              </div>
              <div className="flow-spine-connector">
                <span className="flow-pulse-beam" />
              </div>
              <div className="flow-stage-node right">
                <span className="node-marker" />
                <span className="stage-tag">LOCATION</span>
              </div>
            </div>

            {/* 3-Zone Responsive Command Workspace */}
            <div className="command-workspace-3zone">
              {/* ZONE 1 (Left): Unified WhatsApp-style Conversation Studio */}
              <section className="zone-conversation" aria-label="Conversation Studio">
                <ConversationStudio
                  messages={messages}
                  isProcessing={isProcessing}
                  error={chatError}
                  onSendMessage={handleSendMessage}
                  onSendVoiceMessage={handleSendVoiceMessage}
                  onResetConversation={handleResetConversation}
                  hasCaseCreated={Boolean(createdCase)}
                  createdCaseId={createdCase?.case_id}
                />
              </section>

              {/* ZONE 2 (Center): Civic Intelligence / Extraction HUD */}
              <section className="zone-intelligence" aria-label="Civic Extraction HUD">
                <ExtractionHUD
                  state={canonicalState}
                  isLoading={isProcessing}
                  onOpenDocketReview={() => setIsDocketModalOpen(true)}
                />
              </section>

              {/* ZONE 3 (Right): Live Civic Map */}
              <section className="zone-map" aria-label="Live Civic Signal Map">
                <CivicMap
                  locationName={canonicalState?.location || undefined}
                  landmark={canonicalState?.landmark || undefined}
                  interactive={true}
                  allowManualPin={true}
                  onLocationSelect={(lat, lng, name) => {
                    setSelectedCoordinates({ lat, lng, source: 'MAP_SELECTED' });
                    setConfirmedLocation(name || 'Map-Confirmed Location');
                    setCanonicalState((prev) =>
                      prev
                        ? {
                            ...prev,
                            latitude: lat,
                            longitude: lng,
                            location_source: 'MAP_SELECTED',
                            location: prev.location || name || 'Map-Confirmed Location',
                          }
                        : null
                    );
                  }}
                />
              </section>
            </div>
          </div>
        )}

        {/* TRACK DOCKET VIEW */}
        {activeTab === 'track' && (
          <div className="track-tab-container">
            <TrackingView
              initialCaseId={selectedCaseForTracking}
              recentCaseIds={recentDockets}
              onSelectCaseForEvidence={handleSelectCaseForEvidence}
              initialMode="PUBLIC"
            />
          </div>
        )}

        {/* AUDIT TRAIL VIEW (Directly launched from Nav for Supervisor / Admin) */}
        {activeTab === 'audit' && (
          <div className="track-tab-container">
            <TrackingView
              initialCaseId={selectedCaseForTracking}
              recentCaseIds={recentDockets}
              onSelectCaseForEvidence={handleSelectCaseForEvidence}
              initialMode="AUDIT"
            />
          </div>
        )}

        {/* EVIDENCE STUDIO */}
        {activeTab === 'evidence' && (
          <div className="evidence-tab-container">
            <EvidenceStudio
              initialCaseId={selectedCaseForEvidence || (recentDockets[0] || '')}
              onSuccess={() => {}}
            />
          </div>
        )}
      </main>

      {/* Authentication Login Modal */}
      <LoginModal />

      {/* Action Docket Review Modal */}
      <ActionDocketModal
        isOpen={isDocketModalOpen}
        state={canonicalState}
        onClose={() => setIsDocketModalOpen(false)}
        onSubmitCase={handleCreateCase}
      />

      {/* Architectural Telemetry Footer */}
      <footer className="app-footer">
        <div className="footer-content">
          <div className="footer-brand">
            <span className="footer-dot" />
            <span className="technical-label">
              JARVIS CIVIC // AUTONOMOUS MUNICIPAL DECISION SUPPORT SYSTEM
            </span>
          </div>
          <div className="footer-disclaimer">
            This record is generated by JARVIS Civic and is not proof of official government submission or resolution.
          </div>
        </div>
      </footer>
    </div>
  );
};

export const App: React.FC<{ initialUser?: any; skipInitialCheck?: boolean }> = ({
  initialUser,
  skipInitialCheck,
}) => {
  return (
    <AuthProvider initialUser={initialUser} skipInitialCheck={skipInitialCheck}>
      <WorkspaceProvider>
        <AppContent />
      </WorkspaceProvider>
    </AuthProvider>
  );
};

export default App;
