/**
 * Canonical Data Contracts and Enums for JARVIS Civic Frontend.
 * Perfectly aligned with Backend Canonical Contracts (Phases 1-7).
 */

export enum CivicIntent {
  WATERLOGGING = 'WATERLOGGING',
  ROAD_POTHOLE = 'ROAD_POTHOLE',
  STREETLIGHT_OUTAGE = 'STREETLIGHT_OUTAGE',
  GARBAGE_ACCUMULATION = 'GARBAGE_ACCUMULATION',
  DRAINAGE_BLOCKAGE = 'DRAINAGE_BLOCKAGE',
  WATER_SUPPLY_ISSUE = 'WATER_SUPPLY_ISSUE',
  ELECTRICITY_OUTAGE = 'ELECTRICITY_OUTAGE',
  PUBLIC_INFRASTRUCTURE_DAMAGE = 'PUBLIC_INFRASTRUCTURE_DAMAGE',
  OTHER_CIVIC_ISSUE = 'OTHER_CIVIC_ISSUE',
}

export enum ControlledDepartment {
  MUNICIPAL_CORPORATION = 'MUNICIPAL_CORPORATION',
  PWD_ROADS = 'PWD_ROADS',
  WATER_SUPPLY = 'WATER_SUPPLY',
  ELECTRICITY_UTILITY = 'ELECTRICITY_UTILITY',
  WASTE_MANAGEMENT = 'WASTE_MANAGEMENT',
  DRAINAGE_STORMWATER = 'DRAINAGE_STORMWATER',
  OTHER_MANUAL_REVIEW = 'OTHER_MANUAL_REVIEW',
}

export enum UrgencyLevel {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
  CRITICAL = 'CRITICAL',
}

export enum CaseStatus {
  DRAFT = 'DRAFT',
  DOCKET_CREATED = 'DOCKET_CREATED',
  ROUTING_PREPARED = 'ROUTING_PREPARED',
  SUBMISSION_READY = 'SUBMISSION_READY',
  UNDER_REVIEW = 'UNDER_REVIEW',
  RESOLVED = 'RESOLVED',
}

export enum ApplicationRole {
  CITIZEN = 'CITIZEN',
  AUTHORITY_OFFICER = 'AUTHORITY_OFFICER',
  MUNICIPAL_SUPERVISOR = 'MUNICIPAL_SUPERVISOR',
  ADMINISTRATOR = 'ADMINISTRATOR',
  PUBLIC = 'PUBLIC',
}

export enum EvidenceType {
  TEXT = 'TEXT',
  IMAGE = 'IMAGE',
  AUDIO = 'AUDIO',
  DOCUMENT = 'DOCUMENT',
}

export enum LocationSource {
  TEXT_REFERENCE = 'TEXT_REFERENCE',
  CITIZEN_SELECTED = 'CITIZEN_SELECTED',
  CONFIRMED = 'CONFIRMED',
  UNAVAILABLE = 'UNAVAILABLE',
  MAP_SELECTED = 'MAP_SELECTED',
  GEOCODED = 'GEOCODED',
  UNCONFIRMED = 'UNCONFIRMED',
}

export interface AuditEvent {
  event_id: string;
  case_id?: string | null;
  event_type: string;
  principal_id: string;
  principal_role: string;
  principal_department?: string | null;
  outcome: string;
  previous_status?: string | null;
  new_status?: string | null;
  metadata?: Record<string, any>;
  timestamp: string;
}

export interface CaseHistoryItem {
  milestone_id: string;
  status: string;
  label: string;
  timestamp: string;
  department?: string | null;
  description: string;
  actor_role?: string | null;
  note?: string | null;
  stage?: string;
}

export interface PublicCaseHistoryItem {
  milestone_id: string;
  status: string;
  label: string;
  timestamp: string;
  description: string;
}

export interface StatusTransitionRequest {
  status: CaseStatus;
  note?: string;
}

export interface ResolutionNoteRequest {
  note: string;
}

export interface CanonicalCivicState {
  case_id?: string | null;
  session_id?: string | null;
  intent?: CivicIntent | null;
  department?: ControlledDepartment | null;
  description?: string | null;
  location?: string | null;
  location_text?: string | null;
  landmark?: string | null;
  pincode?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  location_source?: LocationSource | string | null;
  urgency?: UrgencyLevel | null;
  urgency_rationale?: string | null;
  evidence?: EvidenceType[];
  evidence_uris?: string[];
  citizen_language?: string | null;
  language?: string | null;
  confidence?: number | null;
  missing_fields?: string[];
  followup_question?: string | null;
  ready_for_action?: boolean;
  status?: CaseStatus;
  created_at?: string;
  updated_at?: string;
}

export interface ConversationRequest {
  session_id: string;
  message: string;
  language?: string;
}

export interface ConversationResponse {
  session_id: string;
  state: CanonicalCivicState;
  reply?: string | null;
}

export interface CivicCaseCreateRequest {
  description: string;
  location: string;
  department: ControlledDepartment;
  pincode?: string | null;
  is_public?: boolean;
  latitude?: number | null;
  longitude?: number | null;
  location_source?: string | null;
}

export interface CivicCaseRecord {
  case_id: string;
  owner_id: string;
  department: string;
  status: CaseStatus;
  description: string;
  location: string;
  landmark?: string | null;
  pincode?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  location_source?: string | null;
  urgency?: string | null;
  urgency_rationale?: string | null;
  session_id?: string | null;
  is_public: boolean;
  evidence_uris: string[];
  resolution_notes: string[];
  created_at: string;
  updated_at: string;
}

export interface EvidenceMetadata {
  evidence_id: string;
  case_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  s3_key: string;
  s3_uri: string;
  uploaded_at: string;
}

export interface PublicTrackingProjection {
  case_id: string;
  status: string;
  recommended_department: string;
  created_at: string;
  updated_at: string;
}

export type VoiceState = 'IDLE' | 'LISTENING' | 'PROCESSING' | 'READY' | 'ERROR' | 'UNSUPPORTED';

export interface SupportedLocale {
  code: string;
  name: string;
  nativeName: string;
  hint: string;
}

export interface ChatMessage {
  id: string;
  sender: 'citizen' | 'jarvis';
  text: string;
  timestamp: string;
  followupQuestion?: string | null;
  missingFields?: string[];
  readyForAction?: boolean;
  isVoice?: boolean;
  voiceDuration?: string;
  languageHint?: string;
  transcription?: string;
  structuredDetails?: {
    issue?: string;
    location?: string;
    department?: string;
    urgency?: string;
  };
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthenticatedUser {
  principal_id: string;
  email: string;
  display_name: string;
  role: ApplicationRole;
  department?: ControlledDepartment | string | null;
  is_active: boolean;
  created_at: string;
}
