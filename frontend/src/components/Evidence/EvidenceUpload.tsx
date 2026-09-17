import React, { useState, useRef } from 'react';
import { UploadCloud, File, CheckCircle2, AlertCircle, X, Loader2, ShieldCheck } from 'lucide-react';
import { api } from '../../services/api';
import { EvidenceMetadata } from '../../types/civic';
import './EvidenceUpload.css';

interface EvidenceUploadProps {
  caseId: string;
  onUploadSuccess?: (metadata: EvidenceMetadata) => void;
}

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf', '.mp3', '.wav', '.txt'];

export const EvidenceUpload: React.FC<EvidenceUploadProps> = ({ caseId, onUploadSuccess }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadedEvidence, setUploadedEvidence] = useState<EvidenceMetadata[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    if (file.size === 0) {
      return 'Selected file is empty.';
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return `File exceeds maximum allowed limit of 10MB (${(file.size / (1024 * 1024)).toFixed(1)}MB).`;
    }
    const lowerName = file.name.toLowerCase();
    const hasAllowedExt = ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!hasAllowedExt) {
      return `Unsupported file format. Allowed types: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }
    return null;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const validationError = validateFile(file);
      if (validationError) {
        setErrorMessage(validationError);
        setSelectedFile(null);
      } else {
        setErrorMessage(null);
        setSelectedFile(file);
      }
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setErrorMessage(null);

    try {
      const metadata = await api.uploadEvidence(caseId, selectedFile);
      setUploadedEvidence((prev) => [...prev, metadata]);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (onUploadSuccess) onUploadSuccess(metadata);
    } catch (err: any) {
      setErrorMessage(err.message || 'Evidence upload failed.');
    } finally {
      setIsUploading(false);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="evidence-studio" aria-label="Evidence Attachment Studio">
      <div className="evidence-header">
        <div className="evidence-title-box">
          <UploadCloud size={20} color="var(--civic-cyan)" />
          <h3 className="evidence-title">Attach Case Evidence (Photos / Audio / Documents)</h3>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <ShieldCheck size={14} color="var(--civic-emerald)" />
          <span>Cedar Protected</span>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        id="evidence-file-input"
        className="sr-only"
        accept={ALLOWED_EXTENSIONS.join(',')}
        onChange={handleFileChange}
        disabled={isUploading}
        style={{ display: 'none' }}
      />

      {errorMessage && (
        <div className="chat-error-banner" role="alert" style={{ margin: 0 }}>
          <AlertCircle size={16} />
          <span>{errorMessage}</span>
        </div>
      )}

      {!selectedFile ? (
        <label htmlFor="evidence-file-input" className="dropzone-area" tabIndex={0}>
          <UploadCloud size={32} color="var(--civic-cyan)" />
          <div className="dropzone-label">Click or Drag to Upload Evidence</div>
          <div className="dropzone-hint">
            Max 10MB • JPG, PNG, PDF, MP3, WAV, TXT • Secure AWS-compatible storage
          </div>
        </label>
      ) : (
        <div className="file-preview-card">
          <div className="file-meta-box">
            <File size={22} color="var(--civic-cyan)" />
            <div>
              <div className="file-name">{selectedFile.name}</div>
              <div className="file-size">{formatSize(selectedFile.size)}</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              type="button"
              className="btn-remove-file"
              onClick={() => setSelectedFile(null)}
              disabled={isUploading}
              title="Remove selected file"
            >
              <X size={18} />
            </button>
            <button
              type="button"
              className="btn-upload-action"
              onClick={handleUpload}
              disabled={isUploading}
            >
              {isUploading ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> Uploading...
                </>
              ) : (
                <>
                  <UploadCloud size={16} /> Upload to Case
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {uploadedEvidence.length > 0 && (
        <div className="uploaded-list" aria-label="Attached Evidence List">
          {uploadedEvidence.map((ev) => (
            <div key={ev.evidence_id} className="uploaded-item">
              <div className="uploaded-item-meta">
                <CheckCircle2 size={16} />
                <span>
                  <strong>{ev.filename}</strong> ({formatSize(ev.size_bytes)}) — ID: {ev.evidence_id}
                </span>
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Attached to Case {ev.case_id}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
