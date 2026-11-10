import { useRef, useState } from 'react';
import { uploadCadastral, type UploadCadastralResponse } from '../../api/services';
import { ApiError } from '../../api/client';

const ACCEPTED = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff'];
const MAX_MB = 20;

type Props = { onSuccess: (res: UploadCadastralResponse) => void; onSample: () => void };

export function UploadCadastral({ onSuccess, onSample }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    setError(null);
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`File exceeds ${MAX_MB}MB limit.`);
      return;
    }
    setFile(f);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const submit = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await uploadCadastral(file);
      onSuccess(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="st-split">
      <section className="cs-panel">
        <div className="between">
          <span className="eyebrow dim">Cadastral deed input</span>
          <span className="chip">PDF · PNG · JPG · TIFF</span>
        </div>
        <div
          className={`dropzone${dragging ? ' dragging' : ''}`}
          style={{ marginTop: '1rem' }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
        >
          <svg className="icon" viewBox="0 0 24 24" width="28" height="28" aria-hidden>
            <path d="M6 2h8l5 5v15H6Z M14 2v5h5" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <path d="M9 13h7M9 16h7M9 10h3" fill="none" stroke="var(--terra)" strokeWidth="1.4" />
          </svg>
          {file ? (
            <>
              <div className="filename">{file.name}</div>
              <div className="faint">{(file.size / 1024).toFixed(1)} KB</div>
            </>
          ) : (
            <>
              <div>Drop your cadastral survey plan here, or click to browse</div>
              <div className="faint">Up to {MAX_MB} MB</div>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED.join(',')}
            style={{ display: 'none' }}
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
        </div>

        {error && (
          <div className="alert error" style={{ marginTop: '1rem' }}>
            {error}
          </div>
        )}

        <div className="cs-status">
          <span className="faint">One survey plan per design. Scanned or photographed plans work.</span>
          <button className="primary" onClick={submit} disabled={!file || loading}>
            {loading ? (
              <>
                <span className="spinner" aria-hidden /> Analysing plan…
              </>
            ) : (
              'Process my land plan →'
            )}
          </button>
        </div>
      </section>

      <section className="cs-panel">
        <span className="eyebrow">What happens next</span>
        <ol className="st-steps">
          <li>
            <b>Deed reading</b>
            <span>Text, lot number, extent and boundary points are read off the survey plan.</span>
          </li>
          <li>
            <b>Buildable zone</b>
            <span>NBC setbacks for your road access and the district's coverage limit carve out where you can build.</span>
          </li>
          <li>
            <b>Your brief</b>
            <span>Tell us the rooms, floors and style you want; the space budget checks it fits.</span>
          </li>
          <li>
            <b>Three plan options</b>
            <span>Layouts are generated, validated and scored. Pick one to render the full package.</span>
          </li>
        </ol>
        <div className="auth-callout" style={{ marginTop: '1.5rem' }}>
          <div>
            <b>No survey plan handy?</b>
            <span>Continue with a sample two-storey house in Galle.</span>
          </div>
          <button className="sm" onClick={onSample}>
            Use sample data
          </button>
        </div>
      </section>
    </div>
  );
}
