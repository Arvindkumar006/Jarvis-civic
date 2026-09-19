import React, { useState, useRef, useEffect } from 'react';
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  X,
  Loader2,
  ShieldCheck,
  ShieldAlert,
  Plus,
  Image as ImageIcon,
  Music,
  FileCode,
  Lock,
} from 'lucide-react';
import { evidenceApi } from '../../services/api';
import {
  ApplicationRole,
  CivicEvidenceType,
  EvidenceMetadata,
  EvidenceResponse,
  VerificationOutcome,
} from '../../types/civic';
import { useWorkspace } from '../../context/WorkspaceContext';
import './EvidenceUpload.css';

interface EvidenceStudioProps {
  initialCaseId?: string;
  onSuccess?: (metadata: EvidenceResponse | EvidenceMetadata) => void;
}

type UploadState = 'READY' | 'UPLOADING' | 'STORED' | 'FAILED';

interface StagedEvidenceItem {
  id: string;
  file: File;
  previewUrl: string | null;
  fileCategory: 'image' | 'audio' | 'document';
  state: UploadState;
  metadata?: EvidenceResponse | EvidenceMetadata;
  error?: string;
}

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf', '.mp3', '.wav', '.txt'];

export const EvidenceStudio: React.FC<EvidenceStudioProps> = ({ initialCaseId = '', onSuccess }) => {
  const { session } = useWorkspace();
  const [caseId, setCaseId] = useState(initialCaseId);
  const [evidenceType, setEvidenceType] = useState<CivicEvidenceType>(CivicEvidenceType.CASE_EVIDENCE);
  const [resolutionAttempt, setResolutionAttempt] = useState<string>('');
  const [stagedFiles, setStagedFiles] = useState<StagedEvidenceItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadedEvidence, setUploadedEvidence] = useState<(EvidenceResponse | EvidenceMetadata)[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync initialCaseId when changed
  useEffect(() => {
    if (initialCaseId) {
      setCaseId(initialCaseId);
    }
  }, [initialCaseId]);

  const validateFile = (file: File): string | null => {
    if (file.size === 0) {
      return 'Selected file is empty.';
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return `Evidence file exceeds the 10MB limit (${(file.size / (1024 * 1024)).toFixed(1)}MB).`;
    }
    const lowerName = file.name.toLowerCase();
    const hasAllowedExt = ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!hasAllowedExt) {
      return 'Unsupported file format. Allowed: JPG, JPEG, PNG, PDF, MP3, WAV, TXT.';
    }
    return null;
  };

  const getFileCategory = (name: string): 'image' | 'audio' | 'document' => {
    const lower = name.toLowerCase();
    if (lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.png')) return 'image';
    if (lower.endsWith('.mp3') || lower.endsWith('.wav')) return 'audio';
    return 'document';
  };

  const addFile = (file: File) => {
    const err = validateFile(file);
    if (err) {
      setErrorMessage(err);
      return;
    }
    setErrorMessage(null);

    const category = getFileCategory(file.name);
    let previewUrl: string | null = null;
    if (category === 'image') {
      try {
        previewUrl = URL.createObjectURL(file);
      } catch {
        previewUrl = null;
      }
    }

    const newItem: StagedEvidenceItem = {
      id: `stage-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      file,
      previewUrl,
      fileCategory: category,
      state: 'READY',
    };

    setStagedFiles((prev) => [newItem, ...prev]);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      Array.from(e.target.files).forEach(addFile);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      Array.from(e.dataTransfer.files).forEach(addFile);
    }
  };

  const handleUploadItem = async (itemId: string) => {
    if (!caseId.trim()) {
      setErrorMessage('Please specify a valid Case ID to attach evidence.');
      return;
    }

    const item = stagedFiles.find((f) => f.id === itemId);
    if (!item) return;

    // Update state to UPLOADING
    setStagedFiles((prev) =>
      prev.map((f) => (f.id === itemId ? { ...f, state: 'UPLOADING', error: undefined } : f))
    );
    setIsUploading(true);
    setErrorMessage(null);

    try {
      const metadata = await evidenceApi.uploadEvidence(
        caseId.trim(),
        item.file,
        session.role,
        session.principalId,
        session.department,
        evidenceType,
        resolutionAttempt.trim() || undefined
      );
      setStagedFiles((prev) =>
        prev.map((f) => (f.id === itemId ? { ...f, state: 'STORED', metadata } : f))
      );
      setUploadedEvidence((prev) => [metadata, ...prev]);
      if (onSuccess) onSuccess(metadata);
    } catch (err: any) {
      setStagedFiles((prev) =>
        prev.map((f) =>
          f.id === itemId
            ? { ...f, state: 'FAILED', error: err.message || 'Upload rejected by server.' }
            : f
        )
      );
      setErrorMessage(err.message || 'Evidence upload failed. Ensure case exists and role is authorized.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemoveStaged = (itemId: string) => {
    setStagedFiles((prev) => prev.filter((f) => f.id !== itemId));
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  return (
    <div className="civic-evidence-workspace crosshair-corner" aria-label="Evidence Attachment Studio">
      {/* Workspace Header */}
      <div className="evidence-sheet-header">
        <div>
          <div className="evidence-prehead">
            <span className="technical-label">CIVIC RECORD WORKSPACE // S3 PERSISTENCE</span>
          </div>
          <h2 className="evidence-sheet-title">Evidence Attachment Studio</h2>
          <p className="evidence-sheet-sub">
            Civic Evidence & Record Workspace. Attach supporting material to your Civic Action Docket. All uploads undergo server-side Cedar validation.
          </p>
        </div>

        <div className="evidence-cedar-badge" title="Protected by Cedar PEP (Action: add_evidence)">
          <ShieldCheck size={12} color="var(--civic-emerald)" />
          <span>CEDAR PROTECTED</span>
        </div>
      </div>

      {/* Target Case ID Input Bar */}
      <div className="evidence-target-row">
        <label htmlFor="evidence-case-id" className="technical-label">
          TARGET CASE:
        </label>
        <div className="target-input-shell">
          <input
            id="evidence-case-id"
            type="text"
            className="target-case-field"
            placeholder="e.g. NS-CHN-2026-821F"
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
          />
        </div>
      </div>

      {/* Evidence Purpose for Authority Roles */}
      {(session.role === ApplicationRole.AUTHORITY_OFFICER ||
        session.role === ApplicationRole.MUNICIPAL_SUPERVISOR ||
        session.role === ApplicationRole.ADMINISTRATOR) && (
        <div className="evidence-type-bar" style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap' }}>
          <span className="technical-label" style={{ minWidth: '100px' }}>EVIDENCE PURPOSE:</span>
          <button
            type="button"
            className={`btn-stage-type ${evidenceType === CivicEvidenceType.CASE_EVIDENCE ? 'active' : ''}`}
            onClick={() => setEvidenceType(CivicEvidenceType.CASE_EVIDENCE)}
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              background: evidenceType === CivicEvidenceType.CASE_EVIDENCE ? 'rgba(6,182,212,0.2)' : 'transparent',
              color: evidenceType === CivicEvidenceType.CASE_EVIDENCE ? '#06b6d4' : '#94a3b8',
              border: '1px solid #334155',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            DOCKET EVIDENCE
          </button>
          <button
            type="button"
            className={`btn-stage-type ${evidenceType === CivicEvidenceType.RESOLUTION_EVIDENCE ? 'active' : ''}`}
            onClick={() => setEvidenceType(CivicEvidenceType.RESOLUTION_EVIDENCE)}
            style={{
              padding: '4px 10px',
              fontSize: '11px',
              background: evidenceType === CivicEvidenceType.RESOLUTION_EVIDENCE ? 'rgba(16,185,129,0.2)' : 'transparent',
              color: evidenceType === CivicEvidenceType.RESOLUTION_EVIDENCE ? '#10b981' : '#94a3b8',
              border: '1px solid #334155',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            RESOLUTION EVIDENCE
          </button>
          {evidenceType === CivicEvidenceType.RESOLUTION_EVIDENCE && (
            <input
              type="text"
              placeholder="Resolution Reference / Attempt ID"
              value={resolutionAttempt}
              onChange={(e) => setResolutionAttempt(e.target.value)}
              style={{
                background: '#0f172a',
                border: '1px solid #334155',
                color: '#f8fafc',
                fontSize: '11px',
                padding: '4px 8px',
                borderRadius: '4px',
                marginLeft: '8px',
                flex: 1,
                minWidth: '180px',
              }}
            />
          )}
        </div>
      )}

      {errorMessage && (
        <div className="evidence-error-strip" role="alert">
          <AlertCircle size={14} />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* 3-Column Evidence Workspace Layout: Objects on Left, Staging/Preview in Center, Security Pipeline on Right */}
      <div className="evidence-workspace-body">
        {/* COLUMN 1: Evidence Objects */}
        <div className="evidence-col-objects crosshair-corner" aria-label="Evidence Objects">
          <div className="col-header-bar">
            <span className="technical-label">EVIDENCE OBJECTS ({stagedFiles.length})</span>
            <span className="obj-count-tag">{stagedFiles.length > 0 ? `${stagedFiles.length} STAGED` : 'EMPTY'}</span>
          </div>

          {stagedFiles.length === 0 ? (
            <div className="objects-empty-inventory">
              <span className="inv-icon">📂</span>
              <span className="inv-title">No objects attached</span>
              <p className="inv-sub">Stage a photo, audio note, or document from the center console.</p>
              <div className="inv-supported-categories">
                <span className="cat-chip">PHOTO</span>
                <span className="cat-chip">AUDIO</span>
                <span className="cat-chip">DOC</span>
              </div>
            </div>
          ) : (
            <div className="staged-objects-list" aria-label="Staged Evidence Objects">
              <div className="staged-cards-grid">
                {stagedFiles.map((item) => (
                  <div key={item.id} className={`staged-item-card state-${item.state.toLowerCase()}`}>
                    <div className="staged-name-row">
                      <span className="staged-filename" title={item.file.name}>
                        {item.file.name}
                      </span>
                      <span className={`upload-state-pill ${item.state.toLowerCase()}`}>
                        {item.state}
                      </span>
                    </div>

                    <div className="staged-meta-row">
                      <span>{item.file.type || item.fileCategory.toUpperCase()}</span>
                      <span>•</span>
                      <span>{formatSize(item.file.size)}</span>
                    </div>

                    {/* Security Badges on Card */}
                    <div className="card-security-badges-row">
                      <span className="card-sec-badge">
                        <ShieldCheck size={10} color="var(--civic-emerald)" />
                        <span>Cedar ✓</span>
                      </span>
                      <span className="card-sec-badge">
                        <ShieldCheck size={10} color="var(--civic-emerald)" />
                        <span>Ownership ✓</span>
                      </span>
                      {item.state === 'STORED' && (
                        <>
                          <span className="card-sec-badge stored">
                            <CheckCircle2 size={10} color="var(--civic-emerald)" />
                            <span>S3 ✓</span>
                          </span>
                          {item.metadata && 'verification_status' in item.metadata && (
                            <span
                              className="card-sec-badge"
                              style={{
                                color:
                                  (item.metadata as any).verification_status === 'VERIFIED'
                                    ? 'var(--civic-emerald, #10b981)'
                                    : (item.metadata as any).verification_status === 'LIKELY_VERIFIED'
                                    ? 'var(--civic-cyan, #06b6d4)'
                                    : (item.metadata as any).verification_status === 'REJECTED'
                                    ? '#f43f5e'
                                    : '#f59e0b',
                                borderColor: 'currentColor',
                              }}
                              title="Advisory AI-assisted evidence assessment"
                            >
                              <span>{(item.metadata as any).verification_status}</span>
                            </span>
                          )}
                        </>
                      )}
                    </div>

                    {item.state === 'STORED' && item.metadata && 'verification_status' in item.metadata && (
                      <div className="verification-assessment-note" style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                        <span style={{ fontWeight: 600, color: 'var(--civic-cyan, #06b6d4)' }}>AI-assisted evidence assessment:</span>{' '}
                        {(item.metadata as any).verification_reason || 'Verified against case context.'}
                      </div>
                    )}

                    {item.error && <div className="staged-err-text">{item.error}</div>}

                    <div className="staged-action-row">
                      <button
                        type="button"
                        className="btn-remove-stage"
                        onClick={() => handleRemoveStaged(item.id)}
                        disabled={item.state === 'UPLOADING'}
                        title="Remove from workspace"
                      >
                        <X size={12} />
                        <span>Remove</span>
                      </button>

                      {item.state !== 'STORED' && (
                        <button
                          type="button"
                          className="btn-upload-stage"
                          onClick={() => handleUploadItem(item.id)}
                          disabled={item.state === 'UPLOADING' || isUploading}
                        >
                          {item.state === 'UPLOADING' ? (
                            <>
                              <Loader2 size={12} className="animate-spin" />
                              <span>STORING...</span>
                            </>
                          ) : (
                            <>
                              <UploadCloud size={12} />
                              <span>STORE IN S3</span>
                            </>
                          )}
                        </button>
                      )}
                      {item.state === 'STORED' && (
                        <span className="stored-badge">
                          <CheckCircle2 size={13} color="var(--civic-emerald)" />
                          <span>STORED IN S3</span>
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* COLUMN 2: Staging & Preview Area */}
        <div className="evidence-col-staging crosshair-corner" aria-label="Staging and Preview Area">
          <div className="col-header-bar">
            <span className="technical-label">STAGING & PREVIEW AREA</span>
            <span className="obj-count-tag">10MB LIMIT</span>
          </div>

          {/* Compact Drop Area */}
          <div
            className="evidence-dropzone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Upload evidence file"
          >
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={handleFileChange}
              accept=".jpg,.jpeg,.png,.pdf,.mp3,.wav,.txt"
              multiple
            />

            <div className="dropzone-center-icon">
              <Plus size={20} />
            </div>
            <div className="dropzone-primary-text">+ ADD EVIDENCE</div>
            <div className="dropzone-sub-text">Drop files here or click to browse</div>
          </div>

          {/* Compact Quick Category Entry Points */}
          <div className="evidence-quick-categories-bar">
            <span className="technical-label">QUICK STAGE CATEGORY</span>
            <div className="evidence-type-buttons-row">
              <button
                type="button"
                className="btn-evidence-type-chip"
                onClick={() => fileInputRef.current?.click()}
                title="Upload photograph"
              >
                <span>📷 PHOTO</span>
              </button>
              <button
                type="button"
                className="btn-evidence-type-chip"
                onClick={() => fileInputRef.current?.click()}
                title="Upload audio recording"
              >
                <span>🎙 AUDIO</span>
              </button>
              <button
                type="button"
                className="btn-evidence-type-chip"
                onClick={() => fileInputRef.current?.click()}
                title="Upload document"
              >
                <span>📄 DOCUMENT</span>
              </button>
            </div>
          </div>

          {/* Active Preview Stage Box */}
          <div className="active-preview-viewport">
            {stagedFiles.length > 0 ? (
              <div className="staging-preview-container">
                <div className="staging-preview-header">
                  <span className="technical-label">ACTIVE OBJECT PREVIEW</span>
                  <span className="staging-filename-truncate">{stagedFiles[0].file.name}</span>
                </div>

                <div className="staging-preview-body">
                  {stagedFiles[0].fileCategory === 'image' && stagedFiles[0].previewUrl ? (
                    <div className="active-image-preview">
                      <img src={stagedFiles[0].previewUrl} alt={stagedFiles[0].file.name} className="active-img" />
                    </div>
                  ) : stagedFiles[0].fileCategory === 'audio' ? (
                    <div className="active-audio-preview">
                      <Music size={32} color="var(--civic-cyan)" />
                      <div className="audio-scrub-demo">
                        <span className="audio-play-pill">▶ PLAY AUDIO</span>
                        <div className="audio-wave-bars">
                          <span className="wave-bar h1" />
                          <span className="wave-bar h3" />
                          <span className="wave-bar h2" />
                          <span className="wave-bar h4" />
                          <span className="wave-bar h2" />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="active-document-preview">
                      <FileText size={36} color="var(--civic-cyan)" />
                      <span className="doc-type-label">{stagedFiles[0].file.name.split('.').pop()?.toUpperCase()} DOCUMENT</span>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="staging-empty-placeholder">
                <ImageIcon size={28} color="var(--text-dim)" />
                <span className="placeholder-text">Select or drop an object to preview</span>
              </div>
            )}
          </div>

          <div className="evidence-limits-strip">
            Strict Whitelist: <code>.jpg, .jpeg, .png, .pdf, .mp3, .wav, .txt</code> • Max 10 MB per object
          </div>
        </div>

        {/* COLUMN 3: Security Flow Panel */}
        <div className="evidence-col-pipeline crosshair-corner" aria-label="Evidence Security Pipeline">
          <div className="col-header-bar">
            <div className="panel-title-row">
              <Lock size={14} color="var(--civic-cyan)" />
              <span className="technical-label">SECURITY PIPELINE</span>
            </div>
            <span className="cedar-active-pill">CEDAR GUARD</span>
          </div>

          <div className="security-vertical-pipeline">
            {/* Step 1: SELECT */}
            <div className={`pipeline-node ${stagedFiles.length === 0 ? 'node-active' : 'node-passed'}`}>
              <span className="node-step">01</span>
              <div>
                <strong>Select File</strong>
                <p>Stage photo, audio, or document evidence</p>
              </div>
            </div>
            <div className="pipeline-connector">↓</div>

            {/* Step 2: CEDAR POLICY CHECK */}
            <div className={`pipeline-node ${stagedFiles.length > 0 ? (isUploading ? 'node-passed' : 'node-active') : ''}`}>
              <span className="node-step">02</span>
              <div>
                <strong>Cedar Policy Check</strong>
                <p>Verifies active role permissions via PEP</p>
              </div>
            </div>
            <div className="pipeline-connector">↓</div>

            {/* Step 3: OWNERSHIP VALIDATION */}
            <div className={`pipeline-node ${caseId.trim().length > 0 ? (isUploading ? 'node-passed' : 'node-active') : ''}`}>
              <span className="node-step">03</span>
              <div>
                <strong>Ownership Validation</strong>
                <p>Confirms case ownership or officer authority</p>
              </div>
            </div>
            <div className="pipeline-connector">↓</div>

            {/* Step 4: EVIDENCE VALIDATION */}
            <div className={`pipeline-node ${stagedFiles.length > 0 ? (isUploading ? 'node-passed' : 'node-active') : ''}`}>
              <span className="node-step">04</span>
              <div>
                <strong>Evidence Validation</strong>
                <p>Enforces 10MB limit & format whitelist</p>
              </div>
            </div>
            <div className="pipeline-connector">↓</div>

            {/* Step 5: S3 PERSISTENCE */}
            <div className={`pipeline-node ${isUploading ? 'node-pulsing' : uploadedEvidence.length > 0 ? 'node-passed' : ''}`}>
              <span className="node-step">05</span>
              <div>
                <strong>S3 Persistence</strong>
                <p>Isolated UUID object storage & audit trail</p>
              </div>
            </div>
            <div className="pipeline-connector">↓</div>

            {/* Step 6: CIVIC RECORD */}
            <div className={`pipeline-node ${uploadedEvidence.length > 0 ? 'node-passed record-confirmed' : ''}`}>
              <span className="node-step">06</span>
              <div>
                <strong>Civic Record</strong>
                <p>Evidence metadata attached to docket</p>
              </div>
            </div>
          </div>

          <div className="security-whitelist-box">
            <span className="technical-label">AUTHORIZED FORMATS</span>
            <div className="whitelist-tags">
              <span>.jpg</span>
              <span>.jpeg</span>
              <span>.png</span>
              <span>.pdf</span>
              <span>.mp3</span>
              <span>.wav</span>
              <span>.txt</span>
            </div>
          </div>
        </div>
      </div>

      {/* Non-official government notice */}
      <div className="record-disclaimer-box" role="note" style={{ marginTop: '2rem' }}>
        <div className="disclaimer-header-row">
          <ShieldAlert size={14} />
          <span>TRANSPARENT CIVIC NOTICE</span>
        </div>
        <p className="disclaimer-body">
          This record is generated by JARVIS Civic and is not proof of official government submission or resolution.
        </p>
      </div>
    </div>
  );
};
