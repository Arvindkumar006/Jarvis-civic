# JARVIS Civic — Backend

**Positioning:** "Speak. Report. Resolve."  
**Core Value Proposition:** "One conversation → one completed civic action."  
**System Classification:** Prototype civic decision-support and workflow system (Non-government, AI-assisted civic grievance record generator).

---

## 1. Architecture Overview

JARVIS Civic employs a multi-phase, local-first architecture designed for the AWS First Commit hackathon:
- **Phase 1 (Completed):** Canonical Data Contracts, Controlled Enums, Pydantic v2 validation models, and core REST scaffolding.
- **Phase 2 (Completed):** AWS Strands Agents SDK integration, local Ollama model provider abstraction, deterministic fallback reasoning, missing-field detection, and multilingual follow-up composition.
- **Phase 3 (Completed):** Local AWS Cedar Policy Decision Point (PDP), Policy Enforcement Point (PEP), least-privilege policies (`.cedar` & `.cedarschema`), ownership/scope invariants, and append-only audit event stream.
- **Phase 4 (Upcoming):** Dual-mode persistence (LocalStack DynamoDB/S3 + SQLite vault) and ReportLab PDF/QR synthesis.
- **Phase 5 (Upcoming):** React + Vite frontend, Web Audio voice intake, and live Civic Extraction HUD.
- **Phase 6 (Upcoming):** Authority triage console, Cedar permission badges, and audit log.

---

## 2. Phase 3: Local AWS Cedar Authorization & PEP Layer

### Architecture Overview
Protected civic operations pass through a formal Policy Enforcement Point (PEP) which queries the local AWS Cedar Policy Decision Point (PDP):

```text
Application Request
        ↓
FastAPI HTTP Endpoint
        ↓
Policy Enforcement Point (PEP)
        ↓
Local AWS Cedar PDP (cedarpy engine)
        ↓
   ALLOW / DENY
        ↓
Protected Civic Operation
        ↓
Application-Level Append-Only Audit Stream
```

### Application Roles
> [!IMPORTANT]
> **Legal & Ethical Boundary:** JARVIS Civic is a non-government prototype. Cedar authorization represents application-level access control and does not establish official government identity, employee credentials, or municipal legal authority.

- **`CITIZEN`**: Self-service citizen user; can create cases and access/update only their own cases.
- **`AUTHORITY_OFFICER`**: Municipal desk/field officer; restricted strictly to cases within their assigned department scope (`principal.department == resource.department`).
- **`MUNICIPAL_SUPERVISOR`**: Operational manager; authorized for triage, status updates, and inspecting audit logs within their supervisory department.
- **`ADMINISTRATOR`**: System management; universal administrative access and audit log inspection.
- **`PUBLIC`**: Unauthenticated/anonymous public user; restricted strictly to safe public tracking projections (`read_public_tracking`).

### Defined Actions
- `create_case`: Submit a new civic grievance case record (`Citizen`, `Administrator`).
- `read_own_case`: Read full case details (`Citizen` owner, `Administrator`).
- `update_own_case`: Update problem statement or geographic landmark (`Citizen` owner, `Administrator`).
- `read_public_tracking`: Read public redacted progress projection without citizen credentials (`PublicUser`, `Citizen`, `Officer`, `Supervisor`, `Admin`).
- `read_authority_case`: Read case details for municipal triage (`AuthorityOfficer` in-department, `Supervisor`, `Admin`).
- `update_case_status`: Transition case lifecycle status (`AuthorityOfficer` in-department, `Supervisor`, `Admin`).
- `add_resolution_note`: Add official resolution/inspection notes (`AuthorityOfficer` in-department, `Supervisor`, `Admin`).
- `read_audit_log`: Inspect application security audit event stream (`Supervisor` in-department, `Administrator`).

### Enforced Security Invariants
1. **Strict Citizen Ownership:** A `Citizen` can NEVER read or modify another citizen's case (`resource.owner == principal`). Cross-citizen access strictly evaluates to `DENY`.
2. **Citizen Status Protection:** A `Citizen` can NEVER perform authority status transitions or mark cases as resolved.
3. **Department Scope Isolation:** An `AuthorityOfficer` assigned to one department (e.g., `DRAINAGE_STORMWATER`) cannot access or modify cases belonging to another department (e.g., `WASTE_MANAGEMENT`).
4. **Public Safe Tracking:** Public tracking requires NO citizen credentials and returns only safe, redacted tracking projections. Private citizen identities, notes, and authorization internals are never exposed.
5. **Fail-Closed Engine:** If Cedar evaluation encounters syntax errors, missing context, or internal exceptions, it strictly fails closed (`DENY` → HTTP 403 `{"detail": "Authorization denied"}`).
6. **Development Principal Isolation:** Requests without identity headers strictly default to `PUBLIC`. Development headers (`X-Principal-Id`, `X-Principal-Role`, `X-Principal-Department`) serve only as test harnesses and cannot be forged to bypass Cedar policy logic.


---

## 3. Phase 2: AWS Strands Agents & Local LLM Provider

### Multi-Agent Pipeline Specialization
Citizen communication flows through a bounded single-pass pipeline of 4 specialized agents:
1. **Agent 1: Requirement & Intent Analyzer (`RequirementIntentAgent`)**
   - Classifies input into the controlled taxonomy of 9 `CivicIntent` values.
   - Detects natural language/dialect (English, Tamil, Hindi, Telugu, Kannada, Bengali, Marathi, Hinglish).
   - Flags non-civic greetings or gibberish.
2. **Agent 2: Civic Information Extractor (`CivicExtractionAgent`)**
   - Extracts explicit street names, landmarks, 6-digit Indian PIN codes (`^[1-9][0-9]{5}$`), and hazard flags.
   - **Anti-Hallucination Mandate:** Never invents or infers unstated geographic entities; absent fields remain `None`.
3. **Agent 3: Department & Urgency Classifier (`DepartmentUrgencyAgent`)**
   - Maps intent to Controlled Recommended Department.
   - Computes objective risk severity (LOW to CRITICAL) with explainable factual rationale using Strands tools.
4. **Agent 4: Clarification & Follow-Up Agent (`ClarificationAgent`)**
   - Enforces the invariant: `location` is strictly required before `ready_for_action = True`.
   - Generates exactly one polite, targeted follow-up question in the citizen's detected language.

### AWS Strands Integration
- Uses registered Strands tools via `@tool` (`validate_pincode_tool`, `map_department_tool`, `calculate_urgency_tool`, `detect_missing_fields_tool`).
- Implements `LocalStrandsModel(strands.models.Model)` adapter enabling Strands agents to interface with local inference providers.

### Local Ollama Provider & Resilient Deterministic Fallback
- Configurable via `OLLAMA_BASE_URL` (default `http://localhost:11434`) and `JARVIS_LLM_MODEL` (default `llama3.2:3b`).
- **Zero-Crash Offline Resilience:** If Ollama is not installed or running, the backend automatically falls back to deterministic rule/regex reasoning without throwing 500 errors or exposing stack traces.

---

## 4. Getting Started

### Prerequisites
- Python 3.11+ (Python 3.13 recommended)
- Optional for local LLM inference: [Ollama](https://ollama.com/)

### Installation
From the `backend` directory:
```bash
pip install -r requirements.txt
```

### Running Tests
All Phase 1, Phase 2, and Phase 3 tests (80 passed):
```bash
$env:PYTHONPATH="backend"; python -m pytest -v tests
```

### Starting the Backend Server
```bash
$env:PYTHONPATH="backend"; python -m uvicorn app.main:app --reload --port 8000
```
- Health Check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- Interactive API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Citizen Intake: `POST http://127.0.0.1:8000/api/conversation`
- Civic Cases: `POST /api/cases`, `GET /api/cases/{case_id}`, `PATCH /api/cases/{case_id}/status`
- Public Tracking: `GET /api/tracking/{case_id}`
- Security Audit Logs: `GET /api/audit/logs`

---

## 5. Controlled Department & Intent Mappings

| Civic Intent | Recommended Department | Urgency Baseline |
|--------------|------------------------|------------------|
| `WATERLOGGING` | `DRAINAGE_STORMWATER` | MEDIUM / HIGH |
| `DRAINAGE_BLOCKAGE` | `DRAINAGE_STORMWATER` | MEDIUM |
| `ROAD_POTHOLE` | `PWD_ROADS` | MEDIUM / HIGH |
| `STREETLIGHT_OUTAGE` | `MUNICIPAL_CORPORATION` | LOW |
| `GARBAGE_ACCUMULATION` | `WASTE_MANAGEMENT` | MEDIUM |
| `WATER_SUPPLY_ISSUE` | `WATER_SUPPLY` | MEDIUM |
| `ELECTRICITY_OUTAGE` | `ELECTRICITY_UTILITY` | HIGH / CRITICAL |
| `PUBLIC_INFRASTRUCTURE_DAMAGE` | `MUNICIPAL_CORPORATION` | HIGH |
| `OTHER_CIVIC_ISSUE` | `OTHER_MANUAL_REVIEW` | LOW |

---

## 6. Strict Zero-Billing & Ethical Disclaimers

- **Zero Cloud Billing:** Operates 100% locally. No AWS credentials, credit card, paid endpoints, or cloud API keys required.
- **Legal & Ethical Boundary:** All generated outputs are designated as **"AI-generated Civic Action Dockets"** or **"AI-generated civic grievance records"**. The system does not claim official government submission, department acceptance, or legal resolution.
