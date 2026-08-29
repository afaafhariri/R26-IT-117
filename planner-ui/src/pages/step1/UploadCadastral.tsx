import { useRef, useState } from 'react';
import { Card } from '../../components/ui';
import { uploadCadastral, type UploadCadastralResponse } from '../../api/services';
import { ApiError } from '../../api/client';

const ACCEPTED = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff'];
const MAX_MB = 20;

type Props = { onSuccess: (res: UploadCadastralResponse) => void };

export function UploadCadastral({ onSuccess }: Props) {
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
    <div className="stack">
      <div>
        <h1>Design</h1>
        <p className="muted">
          Upload a Sri Lankan cadastral plan — Component 01 reads the land details, applies NBC
          regulations, and generates floor plan options from it.
        </p>
      </div>

      <Card>
        <div
          className={`dropzone${dragging ? ' dragging' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
        >
          <div className="icon">📄</div>
          {file ? (
            <>
              <div className="filename">{file.name}</div>
              <div className="faint">{(file.size / 1024).toFixed(1)} KB</div>
            </>
          ) : (
            <>
              <div>Drop your cadastral plan here, or click to browse</div>
              <div className="faint">PDF, PNG, JPG, TIFF — max {MAX_MB}MB</div>
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
      </Card>

      {error && <div className="alert error">{error}</div>}

      <div className="footer-nav">
        <span />
        <button className="primary" onClick={submit} disabled={!file || loading}>
          {loading ? (
            <>
              <span className="spinner" aria-hidden /> Analysing plan…
            </>
          ) : (
            'Process My Land Plan'
          )}
        </button>
      </div>
    </div>
  );
}
