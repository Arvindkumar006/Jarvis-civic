import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Cpu,
  Layers,
  Globe2,
  Lock,
  Database,
  MapPin,
  FileCheck,
  CheckCircle2,
  AlertTriangle,
  Radio,
  ExternalLink,
  ChevronRight,
  Droplets,
  Zap,
} from 'lucide-react';
import { CivicMap, MapMarkerItem } from '../Map/CivicMap';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useAuth } from '../../context/AuthContext';
import { ApplicationRole } from '../../types/civic';
import { WorkspaceSelector } from '../Workspace/WorkspaceSelector';
import './ProductExperience.css';

interface ProductExperienceProps {
  onStartReport: () => void;
  onExploreTrack: () => void;
  onNavigateToConsole?: () => void;
  onNavigateToAudit?: () => void;
}

// Sample civic markers for Page 1 interactive map
const SAMPLE_CITY_MARKERS: MapMarkerItem[] = [
  {
    id: 'm1',
    lat: 13.0604,
    lng: 80.2496,
    category: 'WATER',
    title: 'Severe Waterlogging',
    subtitle: 'Anna Salai near Thousand Lights metro corridor',
    department: 'DRAINAGE_STORMWATER',
  },
  {
    id: 'm2',
    lat: 13.0418,
    lng: 80.2341,
    category: 'ROAD',
    title: 'Deep Road Pothole',
    subtitle: 'Usman Road Flyover approach lane',
    department: 'PWD_ROADS',
  },
  {
    id: 'm3',
    lat: 13.0067,
    lng: 80.2024,
    category: 'LIGHT',
    title: 'Consecutive Streetlight Blackout',
    subtitle: 'Guindy Industrial Estate 4th Cross',
    department: 'ELECTRICAL_LIGHTING',
  },
  {
    id: 'm4',
    lat: 12.9815,
    lng: 80.218,
    category: 'WASTE',
    title: 'Commercial Garbage Overflow',
    subtitle: 'Velachery Bypass vegetable market walkway',
    department: 'SOLID_WASTE',
  },
];

// Interactive 7-stage pipeline data
interface PipelineStage {
  step: string;
  title: string;
  summary: string;
  badge: string;
  telemetry: {
    raw: string;
    extracted: string;
    rationale: string;
  };
}

const PIPELINE_STAGES: PipelineStage[] = [
  {
    step: '01',
    title: 'SPEAK',
    badge: 'VOICE / NATURAL INPUT',
    summary: 'Citizen states civic grievance naturally in their preferred language.',
    telemetry: {
      raw: '"There is heavy waterlogging outside my apartment near Anna Salai blocking the bus stop."',
      extracted: 'Raw Audio/Text Stream Captured',
      rationale: 'No rigid dropdowns or bureaucratic municipal codes required from the citizen.',
    },
  },
  {
    step: '02',
    title: 'UNDERSTAND',
    badge: 'MULTI-AGENT REASONING',
    summary: 'Strands agent coordinator analyzes intent and checks missing fields.',
    telemetry: {
      raw: 'Parsing civic issue semantics...',
      extracted: 'INTENT: WATERLOGGING_DRAINAGE_DEFECT • MISSING: PINCODE',
      rationale: 'Identifies defect type and formulates single follow-up inquiry without hallucinations.',
    },
  },
  {
    step: '03',
    title: 'LOCATE',
    badge: 'SPATIAL VERIFICATION',
    summary: 'Normalizes textual landmark into geospatial reference.',
    telemetry: {
      raw: '"Anna Salai, near Thousand Lights metro station, Chennai 600006"',
      extracted: 'COORDINATES: 13.0604° N, 80.2496° E • WARD: Zone 09',
      rationale: 'Connects unstructured text to verifiable city grid coordinates.',
    },
  },
  {
    step: '04',
    title: 'CLASSIFY',
    badge: 'MUNICIPAL ONTOLOGY',
    summary: 'Maps defect to controlled canonical schema and urgency rating.',
    telemetry: {
      raw: 'Evaluating traffic hazard & monsoon flood potential...',
      extracted: 'URGENCY: HIGH • CONFIDENCE: 96%',
      rationale: 'Categorized under Drainage & Stormwater with verifiable risk weighting.',
    },
  },
  {
    step: '05',
    title: 'ROUTE',
    badge: 'ROUTING ENGINE',
    summary: 'Recommends competent municipal department automatically.',
    telemetry: {
      raw: 'Recommended Routing: Municipal Corporation (Example Context)',
      extracted: 'RECOMMENDED DEPARTMENT: DRAINAGE_STORMWATER',
      rationale: 'Citizen receives clear routing recommendation across municipal departments.',
    },
  },
  {
    step: '06',
    title: 'DOCKET',
    badge: 'STRUCTURED RECORD',
    summary: 'Synthesizes a structured, AI-generated Civic Action Docket.',
    telemetry: {
      raw: 'DOCKET REF: NS-CHN-2026-821F',
      extracted: 'STATUS: DOCKET CREATED • CEDAR POLICY VALIDATED',
      rationale: 'Server-side validated draft ready for tracking and evidence attachment.',
    },
  },
  {
    step: '07',
    title: 'TRACK',
    badge: 'PUBLIC-SAFE AUDIT',
    summary: 'Transparent 5-stage lifecycle projection protecting citizen privacy.',
    telemetry: {
      raw: 'Monitoring lifecycle progression...',
      extracted: 'CURRENT STATUS: ROUTING PREPARED',
      rationale: 'Only public-safe metadata exposed; private citizen identity strictly preserved.',
    },
  },
];

// Sequential 7-stage Hero Live Transformation Flow
export const HERO_FLOW_STAGES = [
  {
    step: '01',
    label: 'INPUT CAPTURED',
    sub: 'Citizen Speech / Text Input',
    content: '"There is heavy waterlogging near Anna Salai blocking the bus stop..."',
    status: 'INGESTED',
  },
  {
    step: '02',
    label: 'SEMANTIC SIGNAL EXTRACTED',
    sub: 'Strands-Based Intent Reasoning',
    content: 'CIVIC INTENT: WATERLOGGING // DRAINAGE DEFECT',
    status: 'PARSED',
  },
  {
    step: '03',
    label: 'LOCATION REFERENCE FOUND',
    sub: 'Textual Corridor Resolution',
    content: 'LOCATION: Anna Salai (Near Thousand Lights)',
    status: 'RESOLVED',
  },
  {
    step: '04',
    label: 'DEPARTMENT RECOMMENDED',
    sub: 'Jurisdictional Boundary Mapping',
    content: 'RECOMMENDED DEPARTMENT: Drainage / Stormwater • Urgency: Medium',
    status: 'ROUTED',
  },
  {
    step: '05',
    label: 'SCHEMA VALIDATED',
    sub: 'Pydantic Canonical State Guard',
    content: 'Canonical State: Schema Validated (Ready for Action)',
    status: 'VALIDATED ✓',
  },
  {
    step: '06',
    label: 'CEDAR AUTHORIZED',
    sub: 'Policy Enforcement Point Evaluation',
    content: 'permit(principal == Citizen, action == create_case, resource)',
    status: 'ALLOW ✓',
  },
  {
    step: '07',
    label: 'DOCKET READY',
    sub: 'AI-Generated Civic Action Docket',
    content: 'DOCKET ID: NS-CHN-2026-821F // CASE CREATED & PERSISTED',
    status: 'COMPLETED ✓',
  },
];

// Multilingual showcase data (7 Indian languages + Hinglish)
interface LangSample {
  code: string;
  name: string;
  native: string;
  sampleInput: string;
  normalizedIntent: string;
  department: string;
}

const MULTILINGUAL_SAMPLES: LangSample[] = [
  {
    code: 'en-IN',
    name: 'English',
    native: 'English (India)',
    sampleInput: 'Severe waterlogging at Anna Salai near Thousand Lights metro station blocking the entire left lane.',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
  {
    code: 'ta-IN',
    name: 'Tamil',
    native: 'தமிழ்',
    sampleInput: 'அண்ணா சாலையில் ஆயிரம் விளக்கு மெட்ரோ அருகே கடுமையான மழைநீர் தேங்கி போக்குவரத்து பாதிக்கப்பட்டுள்ளது.',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
  {
    code: 'hi-IN',
    name: 'Hindi',
    native: 'हिन्दी',
    sampleInput: 'अन्ना सलाई पर थाउजेंड लाइट्स मेट्रो के पास भारी जलभराव है जिससे सड़क पूरी तरह बंद हो गई है।',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
  {
    code: 'hinglish',
    name: 'Hinglish',
    native: 'Hinglish (Colloquial)',
    sampleInput: 'Anna Salai metro station ke pass bohot paani bhara hua hai, gaadiyan fas rahi hain.',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
  {
    code: 'te-IN',
    name: 'Telugu',
    native: 'తెలుగు',
    sampleInput: 'అన్నా సాలై వద్ద థౌసండ్ లైట్స్ మెట్రో స్టేషన్ సమీపంలో భారీగా నీరు నిలిచిపోయింది.',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
  {
    code: 'kn-IN',
    name: 'Kannada',
    native: 'ಕನ್ನಡ',
    sampleInput: 'ಅಣ್ಣಾ ಸಲೈ ಮೆಟ್ರೋ ನಿಲ್ದಾಣದ ಬಳಿ ರಸ್ತೆಯಲ್ಲಿ ಭಾರಿ ಪ್ರಮಾಣದಲ್ಲಿ ಮಳೆ ನೀರು ನಿಂತಿದೆ.',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
  {
    code: 'bn-IN',
    name: 'Bengali',
    native: 'বাংলা',
    sampleInput: 'আন্না সালাই মেট্রো স্টেশনের কাছে ভয়াবহ জল জমে রাস্তা সম্পূর্ণ অবরুদ্ধ হয়ে পড়েছে।',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
  {
    code: 'mr-IN',
    name: 'Marathi',
    native: 'मराठी',
    sampleInput: 'अण्णा सलाईवर थाउजंड लाइट्स मेट्रो स्थानकाजवळ मोठ्या प्रमाणावर पाणी साचले आहे.',
    normalizedIntent: 'WATERLOGGING_DRAINAGE_DEFECT',
    department: 'Drainage & Stormwater',
  },
];

// Tech stack details
interface TechItem {
  name: string;
  tag: string;
  role: string;
  category: 'AGENTIC' | 'SECURITY' | 'PERSISTENCE' | 'FRONTEND';
}

const TECH_STACK_ITEMS: TechItem[] = [
  {
    name: 'AWS Strands Agents SDK',
    tag: 'MULTI-AGENT COORDINATOR',
    role: 'Coordinates specialized intent, extraction, routing, and urgency agents into an autonomous civic reasoning pipeline.',
    category: 'AGENTIC',
  },
  {
    name: 'Ollama (Local LLM)',
    tag: 'ZERO-COST INFERENCE',
    role: 'Runs open-weight reasoning models locally without external cloud telemetry or recurring API expenses.',
    category: 'AGENTIC',
  },
  {
    name: 'Cedar Policy Engine',
    tag: 'FORMAL AUTHORIZATION',
    role: 'Evaluates role, case ownership, and departmental jurisdiction before allowing any case mutation or evidence attachment.',
    category: 'SECURITY',
  },
  {
    name: 'FastAPI Backend',
    tag: 'HIGH-THROUGHPUT ENGINE',
    role: 'Validates canonical Pydantic contracts and enforces strict fail-closed security at the HTTP boundary.',
    category: 'PERSISTENCE',
  },
  {
    name: 'LocalStack DynamoDB',
    tag: 'CASE PERSISTENCE',
    role: 'Emulates AWS DynamoDB locally with conditional puts to enforce idempotency and append-only audit logs.',
    category: 'PERSISTENCE',
  },
  {
    name: 'LocalStack S3',
    tag: 'EVIDENCE REPOSITORY',
    role: 'Stores photographic and audio evidence with strict MIME validation, UUID isolation, and 10MB limits.',
    category: 'PERSISTENCE',
  },
  {
    name: 'React 19 + TypeScript + Vite',
    tag: 'REACTIVE INTERFACE',
    role: 'Delivers a sub-second, type-safe command workstation with responsive architectural layouts.',
    category: 'FRONTEND',
  },
  {
    name: 'Leaflet + CARTO Basemaps',
    tag: 'HIGH-CONTRAST GEOSPATIAL TILES',
    role: 'Provides interactive city-scale and case-level location mapping using CARTO Dark Matter raster tiles.',
    category: 'FRONTEND',
  },
];

export const ProductExperience: React.FC<ProductExperienceProps> = ({
  onStartReport,
  onExploreTrack,
  onNavigateToConsole,
  onNavigateToAudit,
}) => {
  const { session } = useWorkspace();
  const { role, department } = session;
  const { openLogin } = useAuth();

  const [activePipelineIndex, setActivePipelineIndex] = useState(0);
  const [selectedLang, setSelectedLang] = useState<LangSample>(MULTILINGUAL_SAMPLES[0]);
  const [selectedTech, setSelectedTech] = useState<TechItem>(TECH_STACK_ITEMS[0]);
  const [showCedarDecision, setShowCedarDecision] = useState(false);

  const [currentFlowStep, setCurrentFlowStep] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentFlowStep((prev) => (prev + 1) % HERO_FLOW_STAGES.length);
    }, 2800);
    return () => clearInterval(timer);
  }, []);

  const currentHeroStage = HERO_FLOW_STAGES[currentFlowStep];
  const currentPipeline = PIPELINE_STAGES[activePipelineIndex];

  return (
    <div className="product-experience-view" aria-label="JARVIS Civic Experience">
      {/* 1. HERO SECTION WITH ANIMATED CIVIC SIGNAL FLOW */}
      <section className="experience-hero-section">
        <div className="hero-atmosphere-grid" aria-hidden="true" />

        <div className="hero-brand-lockup">
          <div className="hero-ruler-tag">
            <span className="ruler-line" />
            <span className="ruler-text">
              {role === ApplicationRole.CITIZEN
                ? 'CITIZEN CIVIC WORKSPACE // LIVE INTAKE'
                : role === ApplicationRole.PUBLIC
                ? 'PUBLIC CIVIC TRACKING // ANONYMOUS PROJECTION'
                : role === ApplicationRole.AUTHORITY_OFFICER
                ? 'AUTHORITY WORKSPACE // DEPARTMENTAL REVIEW'
                : role === ApplicationRole.MUNICIPAL_SUPERVISOR
                ? 'SUPERVISOR WORKSPACE // AUDIT & OVERSIGHT'
                : 'ADMINISTRATOR // CIVIC CONTROL PLANE'}
            </span>
            <span className="ruler-line" />
          </div>

          {/* CITIZEN WORKSPACE HERO */}
          {role === ApplicationRole.CITIZEN && (
            <>
              <h1 className="hero-editorial-title">
                Speak. <br />
                Report. <br />
                <span className="title-accent-glow">Resolve.</span>
              </h1>

              <div className="hero-standout-statement">
                <span className="statement-line">Your civic issue starts here.</span>
                <span className="statement-line highlight">One structured civic action.</span>
              </div>

              <p className="hero-narrative-copy">
                Tell JARVIS what needs attention. It understands the issue, identifies what information is missing,
                helps locate it, recommends routing, and creates an AI-generated Civic Action Docket.
              </p>

              <div className="hero-cta-button-row">
                <button
                  type="button"
                  className="btn-hero-primary"
                  onClick={onStartReport}
                >
                  <span>START A CIVIC REPORT</span>
                  <ArrowRight size={16} />
                </button>
                <button
                  type="button"
                  className="btn-hero-secondary"
                  onClick={onExploreTrack}
                >
                  <span>TRACK CASE JOURNEY</span>
                </button>
              </div>
            </>
          )}

          {/* AUTHORITY OFFICER WORKSPACE HERO */}
          {role === ApplicationRole.AUTHORITY_OFFICER && (
            <>
              <h1 className="hero-editorial-title">
                Authorized <br />
                Civic <br />
                <span className="title-accent-glow">Workspace.</span>
              </h1>

              <div className="hero-standout-statement">
                <span className="statement-line">Your authorized civic workspace.</span>
                {department && (
                  <span className="statement-line highlight">
                    Jurisdiction: {department.replace(/_/g, ' ')}
                  </span>
                )}
              </div>

              <p className="hero-narrative-copy">
                Review department-scoped civic action dockets, execute single-step forward lifecycle transitions,
                and inspect attached photographic evidence under server-side Cedar policy enforcement.
              </p>

              <div className="hero-cta-button-row">
                {onNavigateToConsole && (
                  <button
                    type="button"
                    className="btn-hero-primary"
                    onClick={onNavigateToConsole}
                  >
                    <span>ENTER AUTHORITY CONSOLE</span>
                    <ArrowRight size={16} />
                  </button>
                )}
                <button
                  type="button"
                  className="btn-hero-secondary"
                  onClick={onExploreTrack}
                >
                  <span>TRACK CIVIC DOCKET</span>
                </button>
              </div>
            </>
          )}

          {/* MUNICIPAL SUPERVISOR WORKSPACE HERO */}
          {role === ApplicationRole.MUNICIPAL_SUPERVISOR && (
            <>
              <h1 className="hero-editorial-title">
                Municipal <br />
                Workflow <br />
                <span className="title-accent-glow">Oversight.</span>
              </h1>

              <div className="hero-standout-statement">
                <span className="statement-line">Department workflow oversight.</span>
                {department && (
                  <span className="statement-line highlight">
                    Scope: {department.replace(/_/g, ' ')}
                  </span>
                )}
              </div>

              <p className="hero-narrative-copy">
                Supervise departmental civic workflows, enforce canonical lifecycle transitions,
                and inspect authorized append-only Cedar audit events.
              </p>

              <div className="hero-cta-button-row">
                {onNavigateToConsole && (
                  <button
                    type="button"
                    className="btn-hero-primary"
                    onClick={onNavigateToConsole}
                  >
                    <span>ENTER SUPERVISOR CONSOLE</span>
                    <ArrowRight size={16} />
                  </button>
                )}
                <button
                  type="button"
                  className="btn-hero-secondary"
                  onClick={onExploreTrack}
                >
                  <span>TRACK CIVIC DOCKET</span>
                </button>
              </div>
            </>
          )}

          {/* ADMINISTRATOR WORKSPACE HERO */}
          {role === ApplicationRole.ADMINISTRATOR && (
            <>
              <h1 className="hero-editorial-title">
                Administrative <br />
                Civic <br />
                <span className="title-accent-glow">Control Plane.</span>
              </h1>

              <div className="hero-standout-statement">
                <span className="statement-line">Administrative civic control plane.</span>
                <span className="statement-line highlight">Universal Jurisdiction</span>
              </div>

              <p className="hero-narrative-copy">
                Universal access to civic workflows, case triage, and append-only audit trail inspection
                across all municipal department boundaries.
              </p>

              <div className="hero-cta-button-row">
                {onNavigateToConsole && (
                  <button
                    type="button"
                    className="btn-hero-primary"
                    onClick={onNavigateToConsole}
                  >
                    <span>ENTER ADMIN CONSOLE</span>
                    <ArrowRight size={16} />
                  </button>
                )}
                <button
                  type="button"
                  className="btn-hero-secondary"
                  onClick={onExploreTrack}
                >
                  <span>TRACK CIVIC DOCKET</span>
                </button>
              </div>
            </>
          )}

          {/* PUBLIC TRACKING HERO */}
          {role === ApplicationRole.PUBLIC && (
            <>
              <h1 className="hero-editorial-title">
                Public <br />
                Civic <br />
                <span className="title-accent-glow">Tracking.</span>
              </h1>

              <div className="hero-standout-statement">
                <span className="statement-line">Public-safe civic tracking.</span>
                <span className="statement-line highlight">Anonymous Safe Projection</span>
              </div>

              <p className="hero-narrative-copy">
                Track publicly available civic docket progression without an authenticated authority workspace.
                Citizen identity, contact numbers, and private audit trails remain strictly shielded.
              </p>

              <div className="hero-cta-button-row">
                <button
                  type="button"
                  className="btn-hero-primary"
                  onClick={onExploreTrack}
                >
                  <span>TRACK PUBLIC DOCKET</span>
                  <ArrowRight size={16} />
                </button>
              </div>
            </>
          )}
        </div>

        {/* Real Sequential Civic Transformation Visual */}
        <div className="hero-transformation-card crosshair-corner animate-fade-in" aria-label="Civic Transformation Pipeline">
          <div className="trans-header">
            <div className="trans-title-wrap">
              <Sparkles size={14} color="var(--civic-cyan)" />
              <span className="technical-label">LIVE CIVIC TRANSFORMATION // SEQUENTIAL FLOW</span>
            </div>
            <span className="trans-live-pill">● STAGE {currentHeroStage.step} OF 07</span>
          </div>

          {/* Sequential Stepper Strip with Flowing Connectors */}
          <div className="trans-stepper-strip" role="tablist" aria-label="Transformation Stages">
            {HERO_FLOW_STAGES.map((st, idx) => (
              <button
                key={st.step}
                type="button"
                className={`trans-stepper-node ${idx === currentFlowStep ? 'active' : idx < currentFlowStep ? 'passed' : ''}`}
                onClick={() => setCurrentFlowStep(idx)}
                title={`Jump to ${st.label}`}
              >
                <span className="node-dot">{idx < currentFlowStep ? '✓' : st.step}</span>
                <span className="node-name">{st.label.split(' ')[0]}</span>
              </button>
            ))}
          </div>

          {/* Active Transformation Node Telemetry */}
          <div className="trans-active-telemetry-box animate-fade-in" key={currentHeroStage.step}>
            <div className="active-box-top">
              <div className="active-stage-code">
                <span className="code-num">{currentHeroStage.step}</span>
                <span className="code-label">{currentHeroStage.label}</span>
              </div>
              <span className="active-stage-status">{currentHeroStage.status}</span>
            </div>
            <div className="active-stage-sub">{currentHeroStage.sub}</div>
            <div className="active-stage-content">{currentHeroStage.content}</div>
          </div>

          {/* Resulting Structured Transformation Output */}
          <div className="trans-result-breakdown">
            <div className="result-params-grid">
              <div className="param-item">
                <span className="p-key">ISSUE</span>
                <span className="p-val">Waterlogging</span>
              </div>
              <div className="param-item">
                <span className="p-key">LOCATION</span>
                <span className="p-val">Anna Salai</span>
              </div>
              <div className="param-item">
                <span className="p-key">URGENCY</span>
                <span className="p-val urgency">Medium</span>
              </div>
              <div className="param-item">
                <span className="p-key">RECOMMENDED DEPT</span>
                <span className="p-val dept">Drainage / Stormwater</span>
              </div>
            </div>

            {/* Generated Docket Banner */}
            <div className="trans-docket-preview">
              <div className="docket-id-row">
                <span>AI-GENERATED CIVIC ACTION DOCKET:</span>
                <strong>NS-CHN-2026-821F</strong>
              </div>
              <div className="docket-status-tag">SCHEMA VALIDATED • CEDAR AUTHORIZED</div>
            </div>
          </div>

          <div className="trans-legal-notice">
            This record is generated by JARVIS Civic and is not proof of official government submission or resolution.
          </div>
        </div>
      </section>

      {/* 2. INTERACTIVE CITY MAP SECTION (LEAFLET + OPENSTREETMAP) */}
      <section className="experience-map-section">
        <div className="section-header-block">
          <span className="technical-label">URBAN GEOSPATIAL INTELLIGENCE // CHENNAI METROPOLITAN DEMO</span>
          <h2 className="section-heading">Live Civic Signals on City Map</h2>
          <p className="section-subtext">
            Location is fundamental to municipal resolution. Explore sample civic defect reports across the urban corridor.
            Click any pin to inspect the classified defect and recommended department jurisdiction.
          </p>
        </div>

        <div className="city-map-container">
          <CivicMap
            center={[13.045, 80.23]}
            zoom={12}
            markers={SAMPLE_CITY_MARKERS}
            mode="product_visualization"
            interactive={true}
            allowManualPin={false}
            locationName="Chennai Metropolitan Area"
            className="experience-leaflet-map"
          />
        </div>

        <div className="sample-data-notice-bar" role="note">
          <span className="notice-dot" />
          <span className="technical-label">
            SAMPLE GEOSPATIAL DEMO • POWERED BY CARTO DARK MATTER TILES • PRODUCT VISUALIZATION
          </span>
        </div>
      </section>

      {/* 3. SECTION 1: THE PROBLEM VS JARVIS CIVIC */}
      <section className="experience-problem-section">
        <div className="section-header-block">
          <span className="technical-label">WHY JARVIS CIVIC EXISTS</span>
          <h2 className="section-heading">The Bureaucratic Friction</h2>
          <p className="section-subtext">
            "Citizens shouldn't need to know which department handles a problem."
          </p>
        </div>

        <div className="editorial-friction-board crosshair-corner">
          <div className="editorial-side conventional-side">
            <div className="editorial-tag conventional-tag">CONVENTIONAL MUNICIPAL FILING</div>
            <h3 className="editorial-headline">Fragmented Citizen Friction</h3>
            <div className="editorial-friction-items">
              <div className="editorial-item">
                <span className="friction-badge">01</span>
                <div>
                  <strong>Which Department?</strong>
                  <p>Citizens must guess between PWD, GCC, or Metro Stormwater before they can submit.</p>
                </div>
              </div>
              <div className="editorial-item">
                <span className="friction-badge">02</span>
                <div>
                  <strong>Rigid Government Forms</strong>
                  <p>Inflexible portals reject reports if complex ward, zone, or division codes are missing.</p>
                </div>
              </div>
              <div className="editorial-item">
                <span className="friction-badge">03</span>
                <div>
                  <strong>Language Barriers</strong>
                  <p>Demands formal English municipal terminology over native spoken colloquial phrases.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="editorial-transformation-spine">
            <div className="spine-pulse-beam" />
            <div className="spine-step">
              <span className="spine-arrow">→</span>
              <span className="spine-tag">AI RECOMMENDATION</span>
            </div>
            <div className="spine-step">
              <span className="spine-arrow">→</span>
              <span className="spine-tag">CONVERSATIONAL INTAKE</span>
            </div>
            <div className="spine-step">
              <span className="spine-arrow">→</span>
              <span className="spine-tag">MULTILINGUAL INPUT</span>
            </div>
          </div>

          <div className="editorial-side jarvis-side">
            <div className="editorial-tag jarvis-tag">JARVIS CIVIC INTELLIGENCE</div>
            <h3 className="editorial-headline">Single Conversational Action</h3>
            <div className="editorial-solution-items">
              <div className="editorial-item">
                <CheckCircle2 size={18} color="var(--civic-emerald)" />
                <div>
                  <strong>Autonomous Department Routing</strong>
                  <p>Extracts semantics and recommends competent department jurisdiction automatically.</p>
                </div>
              </div>
              <div className="editorial-item">
                <CheckCircle2 size={18} color="var(--civic-emerald)" />
                <div>
                  <strong>Guided Civic Interview</strong>
                  <p>Identifies missing parameters and asks targeted follow-ups in natural conversational language.</p>
                </div>
              </div>
              <div className="editorial-item">
                <CheckCircle2 size={18} color="var(--civic-emerald)" />
                <div>
                  <strong>Multi-Dialect Native Speech</strong>
                  <p>Supports 7 Indian languages plus Hinglish with zero external translation fees.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4. SECTION 2: HOW JARVIS WORKS (INTERACTIVE 7-STAGE PIPELINE) */}
      <section className="experience-pipeline-section">
        <div className="section-header-block">
          <span className="technical-label">INTERACTIVE REASONING LIFECYCLE</span>
          <h2 className="section-heading">How JARVIS Works</h2>
          <p className="section-subtext">
            Click each stage to inspect how citizen words are converted into an authorized municipal record.
          </p>
        </div>

        {/* Connected Horizontal Node Rail */}
        <div className="connected-pipeline-rail" role="tablist" aria-label="Pipeline Stages">
          {PIPELINE_STAGES.map((stage, idx) => {
            const isActive = idx === activePipelineIndex;
            return (
              <React.Fragment key={stage.step}>
                <button
                  type="button"
                  className={`pipeline-rail-node ${isActive ? 'active' : ''}`}
                  onClick={() => setActivePipelineIndex(idx)}
                  role="tab"
                  aria-selected={isActive}
                >
                  <span className="rail-node-step">{stage.step}</span>
                  <span className="rail-node-title">{stage.title}</span>
                  {isActive && <span className="rail-active-beacon" />}
                </button>
                {idx < PIPELINE_STAGES.length - 1 && (
                  <div className={`rail-connector-segment ${idx < activePipelineIndex ? 'passed' : ''}`} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Selected Stage Large Detailed Panel */}
        <div className="pipeline-telemetry-display crosshair-corner animate-fade-in" key={currentPipeline.step}>
          <div className="display-header">
            <div className="display-meta">
              <span className="stage-badge">{currentPipeline.badge}</span>
              <h3 className="stage-title">{currentPipeline.title}: {currentPipeline.summary}</h3>
            </div>
            <span className="technical-label">STAGE {currentPipeline.step} OF 07</span>
          </div>

          <div className="display-body-grid">
            <div className="display-telemetry-cell">
              <span className="cell-label">SYSTEM INPUT / STATE</span>
              <div className="cell-content input-sample">{currentPipeline.telemetry.raw}</div>
            </div>

            <div className="display-telemetry-cell">
              <span className="cell-label">EXTRACTED CIVIC TELEMETRY</span>
              <div className="cell-content output-sample">{currentPipeline.telemetry.extracted}</div>
            </div>
          </div>

          <div className="display-footer-note">
            <span className="technical-label">ARCHITECTURAL RATIONALE:</span>
            <span>{currentPipeline.telemetry.rationale}</span>
          </div>
        </div>
      </section>

      {/* 5. SECTION 3: MULTILINGUAL CIVIC ACCESS (7 LANGUAGES + HINGLISH) */}
      <section className="experience-multilingual-section">
        <div className="section-header-block">
          <span className="technical-label">NATIVE CIVIC ACCESS // 7 INDIAN LANGUAGES + HINGLISH</span>
          <h2 className="section-heading">Speak in Your Mother Tongue</h2>
          <p className="section-subtext">
            Civic action should not require English fluency. Select any language to preview native intake and canonical normalization.
          </p>
        </div>

        {/* Language Tabs */}
        <div className="multilingual-chips-row">
          {MULTILINGUAL_SAMPLES.map((lang) => (
            <button
              key={lang.code}
              type="button"
              className={`lang-select-chip ${selectedLang.code === lang.code ? 'active' : ''}`}
              onClick={() => setSelectedLang(lang)}
            >
              <span className="lang-native">{lang.native}</span>
              <span className="lang-name">{lang.name}</span>
            </button>
          ))}
        </div>

        {/* Interactive Normalization Workspace: Left -> Center -> Right */}
        <div className="multilingual-normalization-flow crosshair-corner animate-fade-in" key={selectedLang.code}>
          <div className="norm-col citizen-col">
            <div className="norm-col-header">
              <Globe2 size={14} color="var(--civic-cyan)" />
              <span className="technical-label">CITIZEN LANGUAGE: {selectedLang.name.toUpperCase()}</span>
            </div>
            <span className="norm-sublabel">RAW INPUT IN {selectedLang.native}</span>
            <blockquote className="native-quote-box">"{selectedLang.sampleInput}"</blockquote>
          </div>

          <div className="norm-col transformation-col">
            <div className="norm-pulse-core">
              <Sparkles size={16} color="var(--civic-cyan)" />
              <span className="technical-label">NORMALIZER</span>
            </div>
            <div className="norm-stream-line">
              <span className="stream-particle" />
            </div>
            <span className="norm-trans-label">SEMANTIC EXTRACTION</span>
          </div>

          <div className="norm-col schema-col">
            <div className="norm-col-header">
              <CheckCircle2 size={14} color="var(--civic-emerald)" />
              <span className="technical-label">CANONICAL CIVIC SCHEMA</span>
            </div>
            <span className="norm-sublabel">STANDARDIZED PARAMETERS</span>
            <div className="canonical-output-card">
              <div className="output-row">
                <span className="out-key">CLASSIFIED DEFECT:</span>
                <span className="out-val">{selectedLang.normalizedIntent}</span>
              </div>
              <div className="output-row">
                <span className="out-key">ROUTED DEPARTMENT:</span>
                <span className="out-val">{selectedLang.department}</span>
              </div>
              <div className="output-row">
                <span className="out-key">STATUS:</span>
                <span className="out-val highlight">SCHEMA VALIDATED • READY FOR DOCKET</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 6. SECTION 4: TRUST + SECURITY (CEDAR POLICY ENGINE) */}
      <section className="experience-security-section">
        <div className="section-header-block">
          <span className="technical-label">FORMAL ACCESS CONTROL // POLICY ENFORCEMENT POINT</span>
          <h2 className="section-heading">Trust, Privacy & Cedar Security</h2>
          <p className="section-subtext">
            Every case mutation and evidence upload is evaluated by the AWS Cedar Policy Engine before execution.
          </p>
        </div>

        {/* Security Flow Diagram: CITIZEN → FASTAPI PEP → CEDAR → AUTHORIZED ACTION → PERSISTENCE */}
        <div className="security-flow-canvas crosshair-corner">
          <div className="security-node-row">
            <div className="sec-node">
              <span className="sec-step">01</span>
              <strong>CITIZEN</strong>
              <span className="sec-desc">Authenticated Actor</span>
            </div>
            <div className="sec-connector active">
              <span className="conn-line" />
              <span className="conn-pulse" />
              <span className="conn-arrow">→</span>
            </div>
            <div className="sec-node">
              <span className="sec-step">02</span>
              <strong>FASTAPI PEP</strong>
              <span className="sec-desc">Policy Enforcement</span>
            </div>
            <div className="sec-connector active">
              <span className="conn-line" />
              <span className="conn-pulse" />
              <span className="conn-arrow">→</span>
            </div>
            <button
              type="button"
              className={`sec-node active ${showCedarDecision ? 'selected' : ''}`}
              onClick={() => setShowCedarDecision((prev) => !prev)}
              aria-label="Inspect Cedar Policy Decision"
              title="Click to inspect live Cedar authorization decision"
            >
              <span className="sec-step">03</span>
              <strong>CEDAR ENGINE</strong>
              <span className="sec-desc">Evaluates Schema</span>
              <span className="sec-click-hint">TAP TO INSPECT</span>
            </button>
            <div className="sec-connector active">
              <span className="conn-line" />
              <span className="conn-pulse" />
              <span className="conn-arrow">→</span>
            </div>
            <div className="sec-node">
              <span className="sec-step">04</span>
              <strong>AUTHORIZED ACTION</strong>
              <span className="sec-desc">Decision: ALLOW</span>
            </div>
            <div className="sec-connector active">
              <span className="conn-line" />
              <span className="conn-pulse" />
              <span className="conn-arrow">→</span>
            </div>
            <div className="sec-node">
              <span className="sec-step">05</span>
              <strong>PERSISTENCE</strong>
              <span className="sec-desc">DynamoDB & S3</span>
            </div>
          </div>

          {/* Interactive Cedar Policy Decision Panel */}
          {showCedarDecision && (
            <div className="cedar-interactive-decision-panel animate-fade-in" role="region" aria-label="Cedar Decision Details">
              <div className="decision-panel-top">
                <div className="decision-title-group">
                  <ShieldCheck size={14} color="var(--civic-emerald)" />
                  <span className="technical-label">LIVE POLICY DECISION // PEP EVALUATION</span>
                </div>
                <span className="decision-allow-pill">DECISION: ALLOW</span>
              </div>

              <div className="decision-grid">
                <div className="decision-cell">
                  <span className="d-key">ACTION:</span>
                  <span className="d-val">Action::"create_case"</span>
                </div>
                <div className="decision-cell">
                  <span className="d-key">PRINCIPAL:</span>
                  <span className="d-val">User::"citizen-chennai-01"</span>
                </div>
                <div className="decision-cell">
                  <span className="d-key">RESOURCE:</span>
                  <span className="d-val">Case::"NS-CHN-2026-821F"</span>
                </div>
                <div className="decision-cell">
                  <span className="d-key">CONTEXT:</span>
                  <span className="d-val">department == "DRAINAGE_STORMWATER"</span>
                </div>
              </div>

              <div className="decision-rule-matched">
                <span>Rule: <code>permit(principal == User::"citizen-chennai-01", action == Action::"create_case", resource);</code></span>
              </div>
            </div>
          )}

          <div className="security-badges-flex">
            <div className="sec-badge">
              <ShieldCheck size={14} color="var(--civic-emerald)" />
              <span>CEDAR PROTECTED</span>
            </div>
            <div className="sec-badge">
              <Lock size={14} color="var(--civic-cyan)" />
              <span>FAIL CLOSED</span>
            </div>
            <div className="sec-badge">
              <CheckCircle2 size={14} color="var(--civic-emerald)" />
              <span>OWNERSHIP ENFORCED</span>
            </div>
            <div className="sec-badge">
              <CheckCircle2 size={14} color="var(--civic-emerald)" />
              <span>DEPARTMENT SCOPED</span>
            </div>
            <div className="sec-badge">
              <CheckCircle2 size={14} color="var(--civic-emerald)" />
              <span>PUBLIC-SAFE TRACKING</span>
            </div>
          </div>
        </div>
      </section>

      {/* 7. SECTION 5: TECHNOLOGY STACK TOPOLOGY */}
      <section className="experience-tech-section">
        <div className="section-header-block">
          <span className="technical-label">ENGINEERING FOUNDATIONS</span>
          <h2 className="section-heading">Modern Architectural Stack</h2>
          <p className="section-subtext">
            Click any component in the system topology to inspect its role and architectural justification.
          </p>
        </div>

        <div className="topology-architecture-layout crosshair-corner">
          <div className="topology-canvas">
            {/* Tier 1: Strands Agents SDK */}
            <div className="topology-tier tier-agents">
              <button
                type="button"
                className={`topo-node ${selectedTech.name.includes('Strands') ? 'active' : ''}`}
                onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('Strands')) || TECH_STACK_ITEMS[0])}
              >
                <div className="topo-node-badge">AGENTIC ORCHESTRATION</div>
                <div className="topo-node-title">AWS Strands Agents SDK</div>
                <div className="topo-node-sub">Multi-Agent Intake Coordinator</div>
              </button>
            </div>

            <div className="topology-down-connector">↓</div>

            {/* Tier 2: Ollama -> Civic Intelligence Engine -> FastAPI PEP */}
            <div className="topology-tier tier-intelligence">
              <button
                type="button"
                className={`topo-node ${selectedTech.name.includes('Ollama') ? 'active' : ''}`}
                onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('Ollama')) || TECH_STACK_ITEMS[1])}
              >
                <div className="topo-node-badge">LOCAL LLM</div>
                <div className="topo-node-title">Ollama Provider</div>
                <div className="topo-node-sub">Mistral / DeepSeek</div>
              </button>

              <div className="topo-h-connector">→</div>

              <button
                type="button"
                className={`topo-node core-node ${selectedTech.name.includes('FastAPI') ? 'active' : ''}`}
                onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('FastAPI')) || TECH_STACK_ITEMS[3])}
              >
                <div className="topo-node-badge">CIVIC CORE</div>
                <div className="topo-node-title">Civic Intelligence + FastAPI</div>
                <div className="topo-node-sub">Async PEP Gateway</div>
              </button>

              <div className="topo-h-connector">→</div>

              <button
                type="button"
                className={`topo-node ${selectedTech.name.includes('Cedar') ? 'active' : ''}`}
                onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('Cedar')) || TECH_STACK_ITEMS[2])}
              >
                <div className="topo-node-badge">AUTHORIZATION</div>
                <div className="topo-node-title">AWS Cedar PDP</div>
                <div className="topo-node-sub">Least-Privilege Guard</div>
              </button>
            </div>

            <div className="topology-down-connector">↓</div>

            {/* Tier 3: DynamoDB & S3 Persistence */}
            <div className="topology-tier tier-storage">
              <div className="topology-storage-split">
                <button
                  type="button"
                  className={`topo-node ${selectedTech.name.includes('DynamoDB') ? 'active' : ''}`}
                  onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('DynamoDB')) || TECH_STACK_ITEMS[4])}
                >
                  <div className="topo-node-badge">PERSISTENCE</div>
                  <div className="topo-node-title">LocalStack DynamoDB</div>
                  <div className="topo-node-sub">JarvisCivicCases Table</div>
                </button>

                <div className="topo-split-divider" />

                <button
                  type="button"
                  className={`topo-node ${selectedTech.name.includes('S3') ? 'active' : ''}`}
                  onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('S3')) || TECH_STACK_ITEMS[5])}
                >
                  <div className="topo-node-badge">EVIDENCE STORE</div>
                  <div className="topo-node-title">LocalStack S3</div>
                  <div className="topo-node-sub">Scoped Evidence Bucket</div>
                </button>
              </div>
            </div>

            {/* Tier 4: Front-of-House */}
            <div className="topology-tier tier-frontend">
              <div className="topology-frontend-bar">
                <button
                  type="button"
                  className={`topo-chip ${selectedTech.name.includes('React') ? 'active' : ''}`}
                  onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('React')) || TECH_STACK_ITEMS[6])}
                >
                  <span>⚛ React + TypeScript + Vite (Client Telemetry Interface)</span>
                </button>
                <span className="topo-link-dot">•</span>
                <button
                  type="button"
                  className={`topo-chip ${selectedTech.name.includes('Leaflet') ? 'active' : ''}`}
                  onClick={() => setSelectedTech(TECH_STACK_ITEMS.find((t) => t.name.includes('Leaflet')) || TECH_STACK_ITEMS[7])}
                >
                  <span>🗺 Leaflet + CARTO Dark Matter (Urban Geospatial Surface)</span>
                </button>
              </div>
            </div>
          </div>

          {/* Active Tech Detail Inspector */}
          <div className="tech-detail-inspector animate-fade-in" key={selectedTech.name}>
            <div className="inspector-head">
              <span className="technical-label">SELECTED ARCHITECTURE NODE</span>
              <span className="tech-tagline-hero">{selectedTech.tag}</span>
            </div>
            <h3 className="inspector-title">{selectedTech.name}</h3>
            <p className="inspector-role">{selectedTech.role}</p>
          </div>
        </div>
      </section>

      {/* 8. FINAL TRANSITION & CTA */}
      <section className="experience-cta-section">
        <div className="cta-inner crosshair-corner">
          <div className="cta-ruler">
            <span className="ruler-line" />
            <span className="ruler-text">READY FOR CIVIC ACTION</span>
            <span className="ruler-line" />
          </div>
          <h2 className="cta-headline">Ready to report something?</h2>
          <p className="cta-sub">
            Speak naturally or type your complaint. JARVIS Civic converts your words into a structured Civic Action Docket.
          </p>
          <div className="cta-actions-row">
            <button
              type="button"
              className="btn-start-report-hero"
              onClick={onStartReport}
            >
              <span>START A CIVIC REPORT</span>
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </section>

      {/* 9. ROLE SELECTION AT BOTTOM OF LANDING PAGE // INTENDED ENTRY POINT */}
      <section className="experience-roles-section" id="role-selection-section" aria-label="Civic Role Selection">
        <div className="experience-section-header">
          <div className="section-ruler-tag">
            <span className="ruler-line" />
            <span className="ruler-text">ACCESS CIVIC WORKSPACE // ROLE SELECTION</span>
            <span className="ruler-line" />
          </div>
          <h2 className="section-headline">Choose Your Civic Role</h2>
          <p className="section-subheadline">
            Select an intended workspace below to sign in. The backend verifies your allocated account credentials and authoritatively determines your actual role and department.
          </p>
        </div>

        <div className="landing-roles-grid">
          {/* CITIZEN */}
          <div className="landing-role-card crosshair-corner" data-testid="role-card-citizen">
            <div className="role-card-header">
              <span className="role-card-index">01</span>
              <span className="role-card-badge badge-citizen">CITIZEN ACCESS</span>
            </div>
            <h3 className="role-card-title">Citizen Workspace</h3>
            <p className="role-card-desc">
              Report civic grievances in plain speech or text, generate structured action dockets, attach photographic proof, and track progress.
            </p>
            <div className="role-card-caps">
              <span className="cap-tag">• Report Issue</span>
              <span className="cap-tag">• Track Docket</span>
              <span className="cap-tag">• Evidence Studio</span>
            </div>
            <button
              type="button"
              className="btn-enter-role-card btn-role-citizen"
              onClick={() => openLogin(ApplicationRole.CITIZEN)}
              aria-label="Enter Citizen Workspace"
            >
              <span>ENTER CITIZEN WORKSPACE</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {/* AUTHORITY OFFICER - DRAINAGE */}
          <div className="landing-role-card crosshair-corner" data-testid="role-card-authority-drainage">
            <div className="role-card-header">
              <span className="role-card-index">02</span>
              <span className="role-card-badge badge-authority">DRAINAGE & STORMWATER</span>
            </div>
            <h3 className="role-card-title">Drainage Officer</h3>
            <p className="role-card-desc">
              Review assigned flood and drainage dockets, inspect coordinates, and execute authorized lifecycle status transitions under Cedar policy.
            </p>
            <div className="role-card-caps">
              <span className="cap-tag">• Authority Console</span>
              <span className="cap-tag">• Track Docket</span>
              <span className="cap-tag">• Assigned Queue</span>
            </div>
            <button
              type="button"
              className="btn-enter-role-card btn-role-authority"
              onClick={() => openLogin(ApplicationRole.AUTHORITY_OFFICER)}
              aria-label="Enter Drainage Officer Workspace"
            >
              <span>ENTER DRAINAGE OFFICER WORKSPACE</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {/* AUTHORITY OFFICER - ROADS */}
          <div className="landing-role-card crosshair-corner" data-testid="role-card-authority-roads">
            <div className="role-card-header">
              <span className="role-card-index">03</span>
              <span className="role-card-badge badge-authority">PWD & ROADS</span>
            </div>
            <h3 className="role-card-title">Roads Officer</h3>
            <p className="role-card-desc">
              Triage pothole and roadway hazard dockets, update maintenance resolutions, and advance status along verified pathways.
            </p>
            <div className="role-card-caps">
              <span className="cap-tag">• Authority Console</span>
              <span className="cap-tag">• Road Hazard Queue</span>
              <span className="cap-tag">• Resolution Notes</span>
            </div>
            <button
              type="button"
              className="btn-enter-role-card btn-role-authority"
              onClick={() => openLogin(ApplicationRole.AUTHORITY_OFFICER)}
              aria-label="Enter Roads Officer Workspace"
            >
              <span>ENTER ROADS OFFICER WORKSPACE</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {/* MUNICIPAL SUPERVISOR */}
          <div className="landing-role-card crosshair-corner" data-testid="role-card-supervisor">
            <div className="role-card-header">
              <span className="role-card-index">04</span>
              <span className="role-card-badge badge-supervisor">SUPERVISORY OVERSIGHT</span>
            </div>
            <h3 className="role-card-title">Municipal Supervisor</h3>
            <p className="role-card-desc">
              Oversee departmental operations, supervise case resolution workflows across all municipal queues, and inspect authorized audit events.
            </p>
            <div className="role-card-caps">
              <span className="cap-tag">• Supervisor Overview</span>
              <span className="cap-tag">• Department Queues</span>
              <span className="cap-tag">• Audit Timeline</span>
            </div>
            <button
              type="button"
              className="btn-enter-role-card btn-role-supervisor"
              onClick={() => openLogin(ApplicationRole.MUNICIPAL_SUPERVISOR)}
              aria-label="Enter Municipal Supervisor Workspace"
            >
              <span>ENTER SUPERVISOR WORKSPACE</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {/* ADMINISTRATOR */}
          <div className="landing-role-card crosshair-corner" data-testid="role-card-admin">
            <div className="role-card-header">
              <span className="role-card-index">05</span>
              <span className="role-card-badge badge-admin">CONTROL PLANE</span>
            </div>
            <h3 className="role-card-title">System Administrator</h3>
            <p className="role-card-desc">
              System-wide administrative visibility, multi-department monitoring, user directory access, and full append-only audit trail inspection.
            </p>
            <div className="role-card-caps">
              <span className="cap-tag">• Admin Operations</span>
              <span className="cap-tag">• User Registry</span>
              <span className="cap-tag">• Full Audit Trail</span>
            </div>
            <button
              type="button"
              className="btn-enter-role-card btn-role-admin"
              onClick={() => openLogin(ApplicationRole.ADMINISTRATOR)}
              aria-label="Enter System Administrator Workspace"
            >
              <span>ENTER SYSTEM ADMINISTRATOR WORKSPACE</span>
              <ArrowRight size={14} />
            </button>
          </div>

          {/* PUBLIC TRACKING */}
          <div className="landing-role-card crosshair-corner" data-testid="role-card-public">
            <div className="role-card-header">
              <span className="role-card-index">06</span>
              <span className="role-card-badge badge-public">ANONYMOUS / PUBLIC</span>
            </div>
            <h3 className="role-card-title">Public Observer</h3>
            <p className="role-card-desc">
              Track public-safe civic docket progression without authority controls or private citizen personal information.
            </p>
            <div className="role-card-caps">
              <span className="cap-tag">• Public Tracking</span>
              <span className="cap-tag">• Lifecycle Journey</span>
              <span className="cap-tag">• No Login Required</span>
            </div>
            <div className="public-card-actions">
              <button
                type="button"
                className="btn-enter-role-card btn-role-public"
                onClick={onExploreTrack}
                aria-label="Continue as Public Observer"
              >
                <span>CONTINUE AS PUBLIC OBSERVER</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
