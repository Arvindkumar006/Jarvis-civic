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

1. **No Paid Cloud Backend Required:** Core application services run locally with zero requirement for billable third-party API endpoints or AWS production credentials.
2. **Canonical Data Contracts (Phase 1):** Controlled civic taxonomies, strict schema enforcement, and explicit support for conversational incomplete states.
3. **Multi-Agent Orchestration (Phase 2):** AWS Strands Agents SDK integration with specialized agent coordination, deterministic trust boundaries, and resilient fallback.
4. **AWS Cedar Authorization (Phase 3):** Formal role-based policy decoupling ensuring verifiable security invariants and principal boundaries.
5. **Dual-Mode Persistence (Phase 4):** LocalStack (DynamoDB + S3) with thread-safe in-memory local persistence fallback.
6. **GovTech Obsidian & Emerald UI (Phase 5):** Tactile dark-mode glassmorphism, responsive Web Speech API voice intake with manual text fallback, and live Civic Extraction HUD.
7. **Authority Workflow & Audit Trail (Phase 6):** Deterministic 5-stage lifecycle state machine with persistent Cedar-governed audit trail.
8. **Production Hardening & Remediation (Phase 7 & Remediation):** Multi-turn session persistence, magic byte & bounded upload validation, public history projection privacy, and durable audit recovery.

---

## Implementation Progress & Verified Git History

- ✅ **Phase 1: Foundation & Data Contracts** (`f050c38`)
- ✅ **Phase 2: AWS Strands Agents & Local LLM Provider** (`2242ddb`)
- ✅ **Phase 3: AWS Cedar Policy Engine & Security** (`64b78c8`)
- ✅ **Phase 4: Persistence Layer & LocalStack Integration** (`f2e0df9`)
- ✅ **Phase 5: Award-Winning Frontend & Voice Studio** (`fa72eb2`)
- ✅ **Phase 6: Authority Workflow & Audit Trail** (`f52c8d7`)
- ✅ **Phase 7: Security Hardening & Live LocalStack Verification** (`fbc84a3`)

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
1. **Production AWS Deployment:** Not deployed to live production AWS infrastructure; runs against local emulation (LocalStack) or in-memory fallback.
2. **Authentication / Identity:** Uses local simulated principal identity headers (`x-jarvis-role`, `x-jarvis-principal-id`); production OAuth2 / OIDC provider is not integrated.
3. **Government Integration:** Not integrated with real municipal or government grievance management APIs; all dockets are citizen-side structured records.
4. **Evidence Scanning:** Evidence pipeline enforces file extension checks, magic-byte signatures, and a 10MB bounded upload limit; deep binary malware scanning is not implemented.
