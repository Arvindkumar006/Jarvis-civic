# JARVIS Civic

> **"Speak. Report. Resolve."**  
> *One conversation → one completed civic action.*

JARVIS Civic is an AI-powered civic decision-support and workflow prototype engineered to convert unstructured, natural-language citizen communication into structured, trackable, and verifiable **AI-generated Civic Action Dockets**.

Target Tracks: **AWS First Commit — Build It Track + Best UI Track**  
System Classification: Prototype civic decision-support and workflow system (Non-government, AI-assisted civic grievance record generator).

---

## Legal & Ethical Disclaimer

**Important Notice:** JARVIS Civic is a technology demonstration prototype designed to assist citizens and community organizations in structuring civic issues. Generated dockets are strictly **"AI-generated civic grievance records"**. The platform does not claim official government submission, department petition acceptance, or statutory legal resolution.

---

## Architectural Principles

1. **No Paid Cloud Backend Required:** Core application services run locally with zero requirement for billable third-party API endpoints or production AWS credentials. Verified against local LocalStack emulation (DynamoDB + S3).
2. **Canonical Data Contracts (Phase 1):** Controlled civic taxonomies, strict schema enforcement, and explicit support for conversational incomplete states with deterministic server-side normalization.
3. **Multi-Agent Orchestration (Phase 2):** AWS Strands Agents SDK runtime (`strands_agent.invoke_async`) with registered civic tools (`extract_civic_data`, `query_pincode_zone`, `lookup_department_jurisdiction`), local Ollama provider (`LocalStrandsModel`), and deterministic fallback.
4. **AWS Cedar Authorization (Phase 3):** Formal role-based policy decoupling with Cedar Policy Engine, fail-closed Policy Enforcement Point (PEP), and active `is_healthy()` readiness check.
5. **Dual-Mode Persistence (Phase 4):** LocalStack (DynamoDB + S3) with thread-safe atomic `list_append` operations and in-memory local persistence fallback.
6. **GovTech Obsidian & Emerald UI (Phase 5):** Tactile dark-mode glassmorphism, responsive Web Speech API voice intake with manual text fallback, live Civic Extraction HUD, and Leaflet/CARTO maps with strict isolation between product visualization demos and real case tracking.
7. **Authority Workflow & Audit Trail (Phase 6):** Deterministic 5-stage lifecycle state machine with persistent Cedar-governed audit trail initialized before request processing.
8. **Security Hardening & Surgical Hardening (Phase 7 & Post-Remediation):** Bounded `cedarpy` and `strands-agents` dependencies, strict binary magic-byte evidence validation, non-civic short-circuiting, public history projection privacy, and atomic concurrent updates.

---

## Session Persistence & State Architecture

- **Conversation Session State:** Multi-turn in-process session state (`LocalConversationSessionRepository`). Sessions retain conversational context and turn history within the running process lifecycle for multi-turn enrichment. In-process session state does not survive server restarts.
- **Durable Case & Audit Storage:** Case records, evidence metadata, lifecycle progression, and audit logs are durably persisted to DynamoDB (or local persistence repository) and S3, surviving service restarts.

---

## Quick Start

### 1. Backend Setup & Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Run Test Suite
```bash
# Backend pytest suite (including live LocalStack verification if container running)
pytest -v tests

# Frontend test suite
cd ../frontend
npm install
npx vitest run
npm run build
npm run typecheck
```

### 3. Start Backend Server
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```
- API Liveness: [http://127.0.0.1:8000/health/live](http://127.0.0.1:8000/health/live)
- API Readiness: [http://127.0.0.1:8000/health/ready](http://127.0.0.1:8000/health/ready)
- API Documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Citizen Intake Endpoint: `POST http://127.0.0.1:8000/api/conversation`

---

## Documented System Limitations

As a prototype civic workflow demonstration:
1. **Prototype Non-Government Status:** Non-government civic technology prototype. JARVIS Civic assists citizens in structuring complaints and recommends civic routing. It does NOT submit complaints to government systems unless an external integration exists, and does NOT claim official government acceptance, inspection, dispatch, resolution, or jurisdiction assignment.
2. **Local Session Scope:** Conversation dialogue sessions are held in-process and reset upon process restart. Case dockets, evidence, and audit logs persist durably.
3. **Authentication / Identity:** Uses simulated principal identity headers (`x-jarvis-role`, `x-jarvis-principal-id`) for simulation and testing. Production OAuth2 / OIDC provider is not integrated, though server-side Cedar PEP strictly validates and enforces role and department boundaries.
4. **Network Dependencies:** Uses CARTO basemap tiles and Google Fonts when online; Leaflet provides graceful offline fallbacks, but the application is not claimed as 100% offline.
5. **Production Cloud Deployment:** Verified against LocalStack local emulation; no production AWS deployment is claimed or configured.
6. **Evidence Scanning:** Enforces strict server-side binary magic-byte signatures (JPEG, PNG, PDF, WAV, MP3), extension allowlist, and 10MB chunked streaming upload validation; deep binary antivirus sandbox scanning is not implemented.
