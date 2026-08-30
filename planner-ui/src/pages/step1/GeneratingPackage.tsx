import { useEffect, useState } from 'react';
import { Bar } from '../../components/ui';

/* Stage 5 (image + text generation) runs as a single request/response on the
 * backend — there's no WebSocket/SSE stream reporting real per-stage
 * progress. This checklist is a timed simulation (same approach Architecture/
 * frontend's own GenerationProgressView.tsx uses), calibrated to typical
 * per-stage durations so it finishes right around when the real response
 * arrives — it is not literally driven by backend state. */
const STAGES = [
  { label: 'Preparing your design data', duration: 3 },
  { label: 'Rendering exterior view', duration: 9 },
  { label: 'Rendering interior view', duration: 9 },
  { label: 'Drawing 2D blueprint', duration: 9 },
  { label: 'Creating 3D floor plan', duration: 9 },
  { label: 'Writing walkthrough script', duration: 5 },
  { label: 'Curating shopping list', duration: 5 },
];

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={3}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

export function GeneratingPackage() {
  const [current, setCurrent] = useState(0);
  const [done, setDone] = useState<boolean[]>(() => new Array(STAGES.length).fill(false));

  useEffect(() => {
    // Guards against React StrictMode's dev-only double-invoke of effects
    // (mount → cleanup → mount) leaving a stray first-instance timer alive.
    let cancelled = false;
    let idx = 0;
    let timer: ReturnType<typeof setTimeout>;

    const advance = () => {
      if (cancelled || idx >= STAGES.length) return;
      setCurrent(idx);
      // Capture the index NOW, by value — setDone's updater function is read
      // by React later (not synchronously here), and `idx` below gets
      // incremented in the meantime. Without this, the updater would close
      // over the *mutated* `idx` and mark the wrong (next) stage done,
      // permanently skipping whichever stage actually just finished.
      const completedIdx = idx;
      timer = setTimeout(() => {
        if (cancelled) return;
        setDone((prev) => {
          const next = [...prev];
          next[completedIdx] = true;
          return next;
        });
        idx++;
        advance();
      }, STAGES[idx].duration * 1000);
    };

    advance();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const totalDone = done.filter(Boolean).length;

  return (
    <div className="stack" style={{ maxWidth: 460, margin: '3rem auto' }}>
      <div style={{ textAlign: 'center' }}>
        <h1>Building Your Full Design Package</h1>
        <p className="muted">{current < STAGES.length ? STAGES[current].label : 'Finalising…'}</p>
      </div>

      <Bar value={totalDone} max={STAGES.length} />

      <div className="stack" style={{ gap: '0.6rem' }}>
        {STAGES.map((stage, i) => {
          const isDone = done[i];
          const isCurrent = i === current && !isDone;
          return (
            <div key={i} className="row" style={{ gap: '0.75rem' }}>
              <span
                style={{
                  width: '1.6rem',
                  height: '1.6rem',
                  borderRadius: '50%',
                  display: 'grid',
                  placeItems: 'center',
                  flexShrink: 0,
                  background: isDone ? 'var(--ok)' : isCurrent ? 'var(--accent)' : 'var(--surface-2)',
                  transition: 'background 0.3s',
                }}
              >
                {isDone ? (
                  <CheckIcon />
                ) : isCurrent ? (
                  <span
                    style={{
                      width: '0.4rem',
                      height: '0.4rem',
                      borderRadius: '50%',
                      background: '#fff',
                      animation: 'bar-pulse 1s ease-in-out infinite',
                    }}
                  />
                ) : (
                  <span className="faint" style={{ fontSize: '0.7rem' }}>
                    {i + 1}
                  </span>
                )}
              </span>
              <span
                style={{
                  flex: 1,
                  fontSize: '0.9rem',
                  color: isDone ? 'var(--text-faint)' : isCurrent ? 'var(--text)' : 'var(--text-faint)',
                  fontWeight: isCurrent ? 600 : 400,
                  textDecoration: isDone ? 'line-through' : 'none',
                }}
              >
                {stage.label}
              </span>
              {isCurrent && <span className="faint mono">running…</span>}
            </div>
          );
        })}
      </div>

      <p className="faint" style={{ textAlign: 'center' }}>
        AI image generation takes ~30–90 seconds. Please wait.
      </p>
    </div>
  );
}
