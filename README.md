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

1. **Zero-Billing & Local-First:** Runs 100% locally with zero requirement for AWS cloud accounts, IAM credentials, credit cards, or billable third-party API endpoints.
2. **Canonical Data Contracts (Phase 1):** Controlled civic taxonomies, strict schema enforcement, and explicit support for conversational incomplete states.
3. **Multi-Agent Orchestration (Phase 2):** AWS Strands Agents SDK integration with specialized agents (Intent Analyzer, Information Extractor, Urgency Classifier, Clarification Agent) and resilient local fallback.
4. **AWS Cedar Authorization (Phase 3):** Formal role-based policy decoupling ensuring verifiable security invariants.
5. **Dual-Mode Persistence (Phase 4):** LocalStack (DynamoDB + S3) with automatic zero-setup SQLite fallback.
6. **GovTech Obsidian & Emerald UI (Phase 5):** Tactile dark-mode glassmorphism, dynamic Web Audio soundwave intake, and live Civic Extraction HUD.

---

## Implementation Progress

- ✅ **Phase 1: Foundation & Data Contracts** (16/16 tests passing)
- ✅ **Phase 2: AWS Strands Agents & Local LLM Provider** (39/39 tests passing)
- ✅ **Phase 3: AWS Cedar Policy Engine & Security** (80/80 tests passing)
- ✅ **Phase 4: Persistence Layer & LocalStack Integration** (101/101 tests passing)
- ⏳ **Phase 5: Award-Winning Frontend & Voice Studio**
- ⏳ **Phase 6: Authority Workflow & Audit Trail**
- ⏳ **Phase 7: Hardening & Polish**

---

## Quick Start (Phase 1 & Phase 2)

### 1. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 2. Run Test Suite
```bash
$env:PYTHONPATH="backend"; python -m pytest -v backend/tests
```

### 3. Start Backend Server
```bash
$env:PYTHONPATH="backend"; python -m uvicorn app.main:app --reload --port 8000
```
- API Health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- API Documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Citizen Intake Endpoint: `POST http://127.0.0.1:8000/api/conversation`
