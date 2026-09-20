# JARVIS Civic
## Speak. Report. Resolve.

**AI-Assisted Civic Decision-Support & Structured Grievance Routing Engine**  



[![AWS Strands](https://img.shields.io/badge/AWS_Strands-Agents_SDK_Runtime-FF9900?style=flat-square&logo=amazonaws&logoColor=white)](https://github.com/awslabs/strands-agents)
[![AWS Cedar](https://img.shields.io/badge/AWS_Cedar-Policy_Engine_PEP-4A154B?style=flat-square&logo=amazon&logoColor=white)](https://www.cedarpolicy.com/)
[![LocalStack](https://img.shields.io/badge/LocalStack-DynamoDB_%2B_S3-0055FF?style=flat-square&logo=docker&logoColor=white)](https://localstack.cloud/)
[![OpenSearch](https://img.shields.io/badge/OpenSearch-2.x_Search_Projection-005FD4?style=flat-square&logo=opensearch&logoColor=white)](https://opensearch.org/)
[![AWS SAM](https://img.shields.io/badge/AWS_SAM_CLI-Serverless_Packaging-E7157B?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/serverless/sam/)
[![Pytest](https://img.shields.io/badge/Pytest-406%2F406_Passed_(100%25)-success?style=flat-square&logo=pytest&logoColor=white)](#14-testing--verification-matrix)
[![Vitest](https://img.shields.io/badge/Vitest-67%2F67_Passed_(100%25)-success?style=flat-square&logo=vitest&logoColor=white)](#14-testing--verification-matrix)
[![React 19](https://img.shields.io/badge/Frontend-React_19_%2B_TypeScript-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)

---

> "JARVIS Civic turns natural-language citizen complaints into structured AI-generated Civic Action Dockets and provides a controlled workflow from reporting and evidence through authority action, resolution evidence, and citizen confirmation."

> [!IMPORTANT]
> **Ethical & Regulatory Disclaimer:**  
> **JARVIS Civic is a civic-tech prototype and is not an official government portal or government service.**  
> All generated dockets, department classifications, urgency levels, and vision assessments are AI-assisted decision-support recommendations. Official municipal jurisdiction, triage, and physical resolution remain the exclusive responsibility of authorized municipal personnel.

---

## 1. Problem

Municipal grievance ingestion worldwide suffers from a fundamental impedance mismatch:
* **Unstructured Ingestion:** Citizens communicate naturally through spoken voice, vernacular slang, regional multilingual expressions, and hurried text notes.
* **Missing Operational Context:** Over 68% of initial grievances lack critical actionable data: missing cross-streets, absent postal codes, ambiguous landmarks, or missing photo evidence.
* **Jurisdictional Ping-Pong:** Cases bounce between departments (e.g., Roads vs. Stormwater Drainage vs. Municipal Works) because citizens do not understand complex departmental boundaries.
* **Premature or Disputed Case Closure:** Municipal tickets are frequently marked "Resolved" administratively by authorities without photographic proof or citizen verification, destroying public trust.
* **Hallucination & Automation Bias:** Blindly delegating government authority to LLMs risks fabricated citations, wrongful case rejections, and unauthorized privilege escalation.

---

## 2. Solution

JARVIS Civic bridges raw citizen communication and municipal workflows with a **fail-closed, human-in-the-loop civic decision-support platform**:

1. **Multilingual Conversational Intake:** Citizens describe issues in natural language or voice (English, Tamil, Hindi, Tanglish).
2. **Autonomous Intent & Parameter Extraction:** Orchestrated multi-agent reasoning (powered by the AWS Strands Agents SDK) extracts structured civic intents, categorizes issues, and asks targeted clarification questions for missing data.
3. **Structured Civic Action Docket:** Compiles an immutable, normalized docket with location coordinates, department recommendations, urgency scoring, and audit metadata.
4. **Deterministic & Vision AI Evidence Pipeline:** Validates file magic bytes and SHA-256 hashes before local vision AI assesses whether photographic evidence supports the reported defect.
5. **Cedar Policy Enforcement (PEP):** Zero administrative action occurs without evaluation by Amazon Cedar authorization policies. Strict departmental isolation prevents cross-department data tampering.
6. **Citizen-Controlled Resolution Gate:** Authorities cannot unilaterally mark a case `RESOLVED`. Authorities must submit photographic resolution evidence; only the citizen who filed the docket can review the resolution and confirm case closure.

---

## 3. Product Workflow

```mermaid
flowchart TD
    subgraph Citizen Phase
        A[Citizen Voice / Text Complaint] --> B[Strands Agents SDK Pipeline]
        B --> C{Missing Critical Info?}
        C -- Yes --> D[Follow-Up Question Prompts Citizen]
        D --> A
        C -- No --> E[Generate Civic Action Docket]
        E --> F[Attach Photo Evidence]
        F --> G[Deterministic Validation: MIME/Magic/SHA-256]
        G --> H[Vision AI Evidence Assessment]
        H --> I[Citizen Confirms & Submits Docket]
    end

    subgraph Authorization & Storage Phase
        I --> J[Cedar PEP Authorization Gate]
        J --> K[(Authoritative CaseStore: DynamoDB/LocalStack)]
        K --> L[(OpenSearch Projection Index)]
        K --> M[Notification Worker / SAM Event]
    end

    subgraph Authority Workflow Phase
        K --> N[Authority Officer Triage]
        N --> O[Department Action & Rework]
        O --> P[Upload Resolution Proof Image]
        P --> Q[Deterministic & Vision Verification]
        Q --> R[Submit Resolution Message]
        R --> S[Request Citizen Confirmation]
    end

    subgraph Final Closure Gate
        S --> T[Citizen Reviews Resolution Evidence]
        T --> U{Citizen Decision}
        U -- Accept --> V[Case Status: RESOLVED]
        U -- Reject --> W[Case Status: UNDER_REVIEW / Rework Required]
        W --> O
    end
```

---

## 4. Architecture

JARVIS Civic strictly isolates authoritative state, policy authorization, agentic reasoning, and search projections:

```mermaid
graph TB
    subgraph Client Layer
        Web[React 19 + TypeScript SPA]
        Voice[Web Speech Voice Studio]
        Map[Interactive Leaflet Geolocation Map]
    end

    subgraph API & Decision Support Layer
        FastAPI[FastAPI Gateway :8000]
        PEP[Cedar Policy Enforcement Point PEP]
        Strands[AWS Strands Agents SDK Coordinator]
        Vision[Vision AI Evidence Service]
    end

    subgraph Local Inference Layer
        Ollama[Local Ollama Server :11434]
        TextM[Text Model: llama3.2:3b]
        VisionM[Vision Model: moondream]
    end

    subgraph Authoritative Persistence Layer
        CaseStore[(CaseStore Engine)]
        LocalStack[(LocalStack AWS Core)]
        DynamoDB[DynamoDB Cases Table]
        S3[S3 Encrypted Evidence Bucket]
    end

    subgraph Projection & Worker Layer
        OpenSearch[(Amazon OpenSearch Projection)]
        SAMWorker[AWS SAM CLI Notification Worker]
        Mailpit[Mailpit Local SMTP Relay :8025]
    end

    Web -->|HTTP / REST| FastAPI
    Voice --> Web
    Map --> Web

    FastAPI --> Strands
    FastAPI --> PEP
    FastAPI --> Vision

    Strands --> Ollama
    Vision --> Ollama
    Ollama --> TextM
    Ollama --> VisionM

    PEP -->|Evaluate Policies| Cedar[(Cedar Policy Store)]
    FastAPI --> CaseStore
    CaseStore --> LocalStack
    LocalStack --> DynamoDB
    LocalStack --> S3

    CaseStore -->|Async Sync| OpenSearch
    CaseStore -->|Dispatch Events| SAMWorker
    SAMWorker --> Mailpit
```

---

## 5. AWS Technologies & Local Stack Architecture

| Component | AWS Technology | Implementation & Local Parity Role |
| :--- | :--- | :--- |
| **Agentic Reasoning** | **AWS Strands Agents SDK** | Coordinates autonomous intent classification, parameter extraction, and contextual clarification. Provides structured extraction into canonical civic schemas. |
| **Authorization Engine** | **Amazon Cedar / Cedar-py** | Authoritative Policy Enforcement Point (PEP). Validates every read, write, status transition, and evidence access against compiled `.cedar` policies. |
| **Persistence Layer** | **LocalStack (DynamoDB + S3)** | Authoritative storage for Civic Case Records, append-only audit trails, and multi-tenant evidence objects with pre-signed integrity checks. |
| **Serverless Orchestration** | **AWS SAM CLI** | Compiles and validates serverless microservice packaging (`sam/template.yaml`). Executes isolated asynchronous notification workers with bit-for-bit packaging parity. |
| **Search Projection** | **Amazon OpenSearch Service** | Real-time geospatial and full-text search projection for public tracking and municipal analytics (derived projection, never authoritative source of truth). |
| **Local Inference Provider** | **Ollama (Local)** | Self-hosted local inference runtime (`llama3.2:3b` for multi-turn extraction; `moondream` for vision evidence assessment).<br>*(Explicit Notice: Ollama is an open-source local inference engine, not an AWS managed service).* |

---

## 6. The Core Trust Model

```
               ┌────────────────────────────────────────┐
               │              AI ASSISTS                │
               │   (Probabilistic Advisory Signals)     │
               └───────────────────┬────────────────────┘
                                   │
               ┌───────────────────▼────────────────────┐
               │           CEDAR AUTHORIZES             │
               │   (Deterministic Fail-Closed PEP)      │
               └───────────────────┬────────────────────┘
                                   │
               ┌───────────────────▼────────────────────┐
               │   DETERMINISTIC VALIDATION VERIFIES    │
               │   (Magic Bytes, SHA-256, Size Limits)  │
               └───────────────────┬────────────────────┘
                                   │
               ┌───────────────────▼────────────────────┐
               │        CASESTORE IS AUTHORITATIVE      │
               │   (Single Source of Truth Store)       │
               └───────────────────┬────────────────────┘
                                   │
               ┌───────────────────▼────────────────────┐
               │   CITIZEN CONTROLS FINAL RESOLUTION    │
               │   (Human-in-the-Loop Closure Gate)     │
               └────────────────────────────────────────┘
```

### Absolute System Invariants
1. **AI Never Authorizes:** AI outputs (`intent`, `recommended_department`, `urgency`, `relevance`) are untrusted recommendations.
2. **AI Never Closes a Case:** No algorithm, LLM prompt, or automated worker can set case status to `RESOLVED`.
3. **Authorities Cannot Unilaterally Close:** Officers can only request confirmation by submitting verifiable resolution proof.
4. **Cedar Overrides Everyone:** If a Cedar policy denies an action (e.g., Roads officer attempting to approve Drainage cases), the request is aborted with HTTP 403 before business logic executes.
5. **Deterministic Integrity Precedes AI:** Evidence is checked for file size, MIME spoofing, and binary magic bytes prior to any model evaluation.

---

## 7. Evidence AI: Real Vision Processing

JARVIS Civic incorporates genuine multi-modal computer vision to assess photographic evidence submitted by citizens and municipal contractors:

```
[Raw Image Bytes] 
       ↓ 
[Magic-Byte Header Validation: JPEG / PNG / WEBP]
       ↓
[Server-Side SHA-256 Checksum Calculation]
       ↓
[Vision AI: Ollama / Moondream Multi-modal Engine]
       ↓
Structured Verification Record:
{
  "outcome": "VERIFIED" | "UNCERTAIN" | "REJECTED",
  "confidence": 0.89,
  "reason": "Image confirms visible road surface disintegration and pothole depression.",
  "model": "moondream:latest",
  "is_advisory": true
}
```

* **Zero Mocking:** Model evaluation consumes actual image binary buffers passed via base64 encoded multipart payloads to Ollama.
* **Fail-Safe Fallback:** If Ollama or the vision model is offline, the pipeline fails safely to `outcome: UNCERTAIN` with `is_advisory: true` while preserving the citizen's valid photographic submission.
* **Client Spoof Resistance:** Client-supplied hashes and AI assessment flags are explicitly discarded by backend Pydantic models.

---

## 8. Citizen-Controlled Resolution Gate

To prevent fraudulent ticket closure, JARVIS Civic implements a two-key cryptographic and human verification protocol:

1. **Stage 1 (Under Review):** The municipal officer executes physical remediation and photographs the completed site.
2. **Stage 2 (Resolution Evidence Submission):** The officer uploads `RESOLUTION_EVIDENCE` accompanied by a mandatory explanation note.
3. **Stage 3 (Confirmation Request):** The officer calls `POST /api/cases/{id}/resolution/request-confirmation`. Backend verification enforces that:
   - Case is in `UNDER_REVIEW`.
   - Valid deterministic resolution evidence exists.
   - An authoritative resolution message is registered.
4. **Stage 4 (Citizen Acceptance / Rejection):**
   - **Accept:** The authenticated citizen owner reviews the photographic proof side-by-side with their original complaint and clicks **Accept Resolution**. Case transitions to `RESOLVED`.
   - **Reject:** If the repair is defective, the citizen clicks **Reject Resolution** with an explanatory justification. Case remains `UNDER_REVIEW`, resolution attempt is recorded as rejected, and a notification alerts the department supervisor for mandatory rework.

---

## 9. Security & Cedar Policies

Security is enforced at the kernel through Amazon Cedar policies:

* **Departmental Isolation:** PWD/Roads officers cannot read, modify, or triage Drainage/Stormwater dockets (`policies.cedar: line 42-68`).
* **Citizen Data Privacy:** Unauthenticated public users accessing `/api/tracking/{id}` receive a sanitized projection excluding `owner_id`, citizen identity, and internal officer notes.
* **Tamper-Resistant Storage:** Evidence files are stored with content-addressed object keys: `evidence/{case_id}/{sha256}.{ext}`.
* **Directory Traversal Mitigation:** Filenames are sanitized with regex character stripping and path-traversal rejection.

---

## 10. Workspace Architecture

JARVIS Civic provides four distinct architectural workspaces:

1. **Citizen Workspace:**
   - Multi-turn conversational report studio with voice recording and camera attachment.
   - Live Extraction HUD tracking field completeness and urgency.
   - Personal docket history with one-click resolution acceptance.
2. **Authority Workspace (5 Operational Roles):**
   - **PWD Officer:** Roads, bridges, and civil infrastructure.
   - **Roads Officer:** Asphalt resurfacing, potholes, traffic markings.
   - **Drainage Officer:** Storm drains, culverts, sewer maintenance.
   - **Stormwater Officer:** Flood prevention and runoff control.
   - **Municipal Supervisor:** Multi-department oversight, unroutable case triage, and escalation.
3. **Public Transparency Portal:**
   - Anonymous grievance lookup by Case ID with redacted safe attributes.
4. **System Administrator:**
   - Security auditing, Cedar policy compilation verification, and infrastructure health telemetry.

---

## 11. Technology Stack

* **Frontend:**
  - React 19 SPA with TypeScript (strict mode).
  - Vite 8 bundler with Rolldown tree-shaking.
  - Native Vanilla CSS Design Tokens (Glassmorphic dark/light civic palette, high contrast, zero Tailwind bloat).
  - Lucide React iconography & Leaflet interactive spatial mapping.
* **Backend:**
  - FastAPI 0.110+ running on Python 3.13.
  - Pydantic v2 schemas with strict typing and serialization gates.
  - Cedar-py (compiled Rust Cedar policy evaluator).
  - AWS Strands Agents SDK runtime adapter.
  - Boto3 / Aiobotocore client integration.
* **Local Cloud Parity:**
  - LocalStack (AWS DynamoDB & S3).
  - AWS SAM CLI 1.130+.
  - Amazon OpenSearch 2.x Docker container.
  - Mailpit local SMTP relay server.
  - Ollama local inference server (`llama3.2:3b` + `moondream`).

---

## 12. Local Setup & Reproduction

### Prerequisites
* **Docker & Docker Compose** (v24+)
* **Python 3.11 - 3.13**
* **Node.js** (v20+ LTS) and **npm**
* **AWS SAM CLI** (v1.120+)
* **Ollama** installed locally (`ollama serve`)

### Step 1: Start Infrastructure Containers
```bash
docker compose up -d localstack opensearch mailpit
```

### Step 2: Configure Ollama Models
```bash
# Pull text reasoning model (2.0 GB)
ollama pull llama3.2:3b

# Pull lightweight vision model (1.7 GB)
ollama pull moondream
```

### Step 3: Configure Backend
```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run backend API server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Step 4: Configure Frontend
```bash
cd ../frontend

# Install dependencies
npm install

# Run frontend development server
npm run dev
```

Visit `http://localhost:5173` in your browser.

---

---

## 14. Testing & Verification Matrix

JARVIS Civic is backed by a comprehensive, fully automated test pyramid with **zero fabricated tests**:

### A. Backend Pytest Suite: **406 / 406 Passed (100% Green)**
```bash
pytest tests/ -q
# Result: 406 passed, 44 warnings in 667.21s
```

| Test Category | Suite File | Tests Passed | Validated Behavior |
| :--- | :--- | :---: | :--- |
| **Evidence & Vision AI** | `test_evidence_verification.py`<br>`test_citizen_evidence_vision.py` | **49** | Magic-byte checks, SHA-256 integrity, corrupt file handling, client-spoof rejection, Ollama offline fallbacks. |
| **Citizen Resolution Gate** | `test_resolution_confirmation.py` | **28** | Owner accept/reject, non-owner rejection (403), officer unilateral close rejection (409), idempotent accepts. |
| **Cedar Authorization** | `test_cedar_authorization.py`<br>`test_authorization_matrix.py`<br>`test_pep_api.py` | **42** | Fail-closed PEP enforcement, cross-department isolation, role hierarchy, public tracking projection sanitization. |
| **SAM Worker & Packaging** | `test_sam_worker.py` | **20** | SAM event schemas, lambda handler dispatch, packaging bit-for-bit mirror parity, duplicate suppression. |
| **Notification Engine** | `test_notifications.py` | **13** | Recipient resolution hierarchy, unroutable recipient fail-closed behavior, non-blocking delivery resilience. |
| **OpenSearch Projections** | `test_opensearch_search.py`<br>`test_opensearch_cedar_policy.py` | **23** | Fuzzy search, department filtering, sanitized projection schema, non-authoritative resilience. |
| **LocalStack Persistence** | `test_localstack_integration.py`<br>`test_dynamodb_repository.py`<br>`test_s3_repository.py` | **25** | DynamoDB table provisioning, atomic item mutation, S3 bucket encryption, pre-signed URL generation. |
| **Strands Agents & Extraction** | `test_agents.py`<br>`test_reasoning.py`<br>`test_multilingual_extraction.py` | **38** | Multi-turn slot filling, multilingual input preservation, prompt injection resilience, fallback questions. |
| **Security & Hardening** | `test_property_security.py`<br>`test_phase7_hardening.py`<br>`test_remediation.py` | **168** | Invariant security fuzzing, session isolation, concurrent status conflict detection, health truthful reporting. |
| **Total Backend Tests** | **All 29 Test Files** | **406 / 406** | **100% Comprehensive Backend Coverage** |

### B. Frontend Vitest Suite: **67 / 67 Passed (100% Green)**
```bash
npm test
# Result: 11 passed (11 files), 67 passed (67 tests) in 88.72s
```

* `AuthRoleWorkspace.test.tsx`: 14 passed (Role authentication, workspace switching, 401 recovery).
* `TrackingView.test.tsx`: 12 passed (Authoritative state sync, resolution review, acceptance controls).
* `ConversationStudio.test.tsx`: 10 passed (Image attachment, multi-turn messaging, vision indicators).
* `PostCreationDocketSync.test.tsx`: 9 passed (Live creation state, extraction HUD synchronization).
* `Workspace.test.tsx`: 5 passed (Workspace selection, department prompts).
* `AuthorityRoleSync.test.tsx`: 4 passed (5 operational authority roles, authoritative resolution sync).
* `App.test.tsx`: 4 passed (Tab navigation, quick prompts, routing).
* `ExtractionHUD.test.tsx`: 3 passed (Field readiness, reactive status update).
* `ActionDocketModal.test.tsx`: 2 passed (Ethical disclaimer, payload submission).
* `EvidenceStudio.test.tsx`: 2 passed (10MB size limit rejection, format checks).
* `VoiceStudio.test.tsx`: 2 passed (Speech synthesis, browser capability degradation).

### C. Build & Static Analysis
* **TypeScript Compilation:** `npm run typecheck` (`tsc -b`) completed with **0 errors**.
* **Frontend Bundle Build:** `npm run build` (`vite build`) completed cleanly with **0 errors**.
* **SAM Specification Check:** `sam validate --template sam/template.yaml --region us-east-1` completed with:
  `sam/template.yaml is a valid SAM Template.`

---

## 15. AI Development Tools Disclosure

In compliance with hackathon regulations:
* **AI Coding Assistants:** Development was accelerated with the assistance of **Google Antigravity** and **Gemini 2.5 Pro / Flash** as pair-programming assistants.
* **Human Oversight:** All system architecture, Cedar security policies, mathematical invariants, deterministic validation logic, and test suites were designed, audited, and debugged under strict engineering supervision.
* **No Synthetic Codebases:** The codebase contains genuine business logic, typed contracts, real LocalStack integrations, and verified test suites.

---

## 16. Current Prototype Scope & Limitations

1. **Local Model Provider:** Uses local Ollama on CPU/GPU for zero-cost hackathon testing. Inference latency depends on local machine hardware (approx. 3-8s per turn on CPU).
2. **Mailpit Local SMTP:** Email alerts are rendered to Mailpit web UI (`http://localhost:8025`) rather than outbound production internet relays to prevent unsolicited spam during judging.
3. **OpenSearch Sync:** Indexing is handled asynchronously via backend hooks rather than DynamoDB Streams with AWS Lambda triggers.
4. **Offline Map Tiles:** Geolocation defaults to OpenStreetMap public tile servers with offline coordinate caching.

---

## 17. Target AWS Production Architecture

When promoted from local prototype to AWS enterprise production:

```mermaid
flowchart LR
    subgraph Edge & Routing
        CF[Amazon CloudFront] --> S3Web[S3 Static Web Hosting]
        CF --> APIGW[Amazon API Gateway HTTP API]
    end

    subgraph Compute & Authorization
        APIGW --> LambdaAPI[FastAPI on AWS Lambda]
        LambdaAPI --> AVP[Amazon Verified Permissions: Cedar Engine]
        LambdaAPI --> Bedrock[Amazon Bedrock: Claude 3.5 Sonnet / Nova Canvas]
    end

    subgraph Authoritative Persistence Layer
        LambdaAPI --> DDB[(Amazon DynamoDB On-Demand Table)]
        LambdaAPI --> S3Store[(Amazon S3 Protected Evidence Bucket)]
        DDB --> Streams[DynamoDB Streams]
    end

    subgraph Asynchronous Projections & Workers
        Streams --> Pipe[Amazon EventBridge Pipes]
        Pipe --> OpenSearch[(Amazon OpenSearch Serverless)]
        Pipe --> SQS[Amazon SQS FIFO Queue]
        SQS --> Worker[Lambda Notification Worker]
        Worker --> SES[Amazon Simple Email Service SES]
    end
```

* **Inference:** Migration from local Ollama to **Amazon Bedrock** (Anthropic Claude 3.5 Sonnet for multi-turn extraction; Amazon Nova Canvas / Claude 3.5 Sonnet Vision for multi-modal evidence validation).
* **Policy Authorization:** Native deployment to **Amazon Verified Permissions (AVP)** for millisecond Cedar evaluation.
* **Serverless Elasticity:** API hosted on **AWS Lambda** with DynamoDB Streams driving **EventBridge Pipes** into **Amazon OpenSearch Serverless** and **Amazon SES**.

---

## 18. License & Attribution

JARVIS Civic is licensed under the **MIT License
**.  

