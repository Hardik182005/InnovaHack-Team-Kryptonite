/** Upload page — §6.2. */

import { ChangeEvent, DragEvent, FormEvent, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { api } from '../api/client';
import { ErrorState, SectionHead } from '../components/common';
import { useMutation } from '../hooks/useResource';
import { formatBytes } from '../lib/format';

const ACCEPTED = ['.pdf', '.csv', '.xlsx', '.xls', '.txt'];
const MAX_BYTES = 15 * 1024 * 1024;

interface FileProblem {
  code: 'type' | 'size' | 'empty';
  message: string;
}

function validateFile(file: File): FileProblem | null {
  const lower = file.name.toLowerCase();
  if (!ACCEPTED.some((ext) => lower.endsWith(ext))) {
    return {
      code: 'type',
      message: `That file type is not supported. Upload a PDF, CSV or XLSX statement.`,
    };
  }
  if (file.size === 0) {
    return { code: 'empty', message: 'That file is empty.' };
  }
  if (file.size > MAX_BYTES) {
    return {
      code: 'size',
      message: `That file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_BYTES)}.`,
    };
  }
  return null;
}

export default function Upload() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const demoRequested = params.get('demo') === '1';

  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<FileProblem | null>(null);
  const [dragging, setDragging] = useState(false);
  const [consent, setConsent] = useState(false);
  const [deleteAfter, setDeleteAfter] = useState(true);
  const [password, setPassword] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const start = useMutation(async (useDemo: boolean) => {
    let uploadId: string | undefined;
    if (!useDemo && file) {
      const grant = await api.presignUpload({
        filename: file.name,
        content_type: file.type || 'application/octet-stream',
        size_bytes: file.size,
      });
      uploadId = grant.upload_id;
      await api.uploadContent?.(grant, file);
    }
    const ref = await api.createAnalysis({
      upload_id: uploadId,
      demo: useDemo,
      document_password: password || undefined,
      consent_confirmed: true,
      delete_after_processing: deleteAfter,
    });
    navigate('/processing');
    return ref;
  });

  const isPdf = useMemo(() => file?.name.toLowerCase().endsWith('.pdf') ?? false, [file]);

  function accept(next: File | null) {
    setProblem(null);
    if (!next) {
      setFile(null);
      return;
    }
    const issue = validateFile(next);
    if (issue) {
      setProblem(issue);
      setFile(null);
      return;
    }
    setFile(next);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files?.[0] ?? null);
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    accept(event.target.files?.[0] ?? null);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!consent) return;
    void start.run(false);
  }

  return (
    <div className="wrap section">
      <SectionHead
        eyebrow="Step 1 of 3"
        title="Upload a statement"
        lede="A digital PDF or a CSV export works best. Nothing is connected to your bank, and no money is ever moved."
      />

      {demoRequested ? (
        <div className="notice notice--positive" style={{ marginBottom: 24 }}>
          <p className="prose">
            The demo uses a <strong>synthetic statement</strong> — six months of invented
            transactions. No real account is involved.
          </p>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void start.run(true)}
            disabled={start.pending}
          >
            {start.pending ? 'Starting…' : 'Analyze the demo statement'}
          </button>
        </div>
      ) : null}

      {start.error ? <ErrorState error={start.error} /> : null}

      <form onSubmit={onSubmit} className="grid grid--2">
        <div className="stack">
          <div
            className={dragging ? 'dropzone dropzone--on' : 'dropzone'}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            role="button"
            tabIndex={0}
            aria-describedby="upload-help"
          >
            <p className="display-4">{file ? file.name : 'Drop your statement here'}</p>
            <p className="micro t-muted">
              {file ? formatBytes(file.size) : `PDF, CSV or XLSX · up to ${formatBytes(MAX_BYTES)}`}
            </p>
            <input
              ref={inputRef}
              type="file"
              className="sr-only"
              accept={ACCEPTED.join(',')}
              onChange={onPick}
              aria-label="Choose a statement file"
            />
          </div>

          <p id="upload-help" className="micro t-muted">
            Supported: digital PDF, CSV, XLSX. Scanned statements are accepted but need review.
          </p>

          {problem ? (
            <p className="notice notice--warning" role="alert">
              {problem.message}
            </p>
          ) : null}
        </div>

        <div className="stack">
          {isPdf ? (
            <div className="field">
              <label htmlFor="pdf-password">PDF password (only if protected)</label>
              <input
                id="pdf-password"
                className="input"
                type="password"
                autoComplete="off"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="micro t-muted">Used once to open the file, then discarded.</p>
            </div>
          ) : null}

          <label className="checkline">
            <input
              type="checkbox"
              checked={deleteAfter}
              onChange={(e) => setDeleteAfter(e.target.checked)}
            />
            Delete the uploaded file once processing finishes
          </label>

          <label className="checkline">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              required
              aria-describedby="consent-help"
            />
            I consent to this statement being analysed
          </label>
          <p id="consent-help" className="micro t-muted">
            SafeSpare reads the statement to categorise spending and calculate what is safely
            spare. It never invests, transfers or cancels anything.
          </p>

          <button
            type="submit"
            className="btn btn--primary btn--lg btn--block"
            disabled={!file || !consent || start.pending}
          >
            {start.pending ? 'Starting…' : 'Analyze my spending'}
          </button>
        </div>
      </form>
    </div>
  );
}
