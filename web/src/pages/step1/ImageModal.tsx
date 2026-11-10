import { useEffect } from 'react';

type Props = { label: string; base64: string; onClose: () => void };

/** Full-size preview + download for one generated render. Download works via
 *  a plain <a download> on the same base64 data URI — this is a normal local
 *  app running in the user's own browser, so that needs no extra handling. */
export function ImageModal({ label, base64, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const dataUrl = `data:image/png;base64,${base64}`;
  const filename = `${label.toLowerCase().replace(/\s+/g, '-')}.png`;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="between" style={{ marginBottom: '0.75rem' }}>
          <h3>{label}</h3>
          <div className="row">
            <a className="btn-link" href={dataUrl} download={filename}>
              ⬇ Download
            </a>
            <button className="ghost" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>
        <img src={dataUrl} alt={label} />
      </div>
    </div>
  );
}
