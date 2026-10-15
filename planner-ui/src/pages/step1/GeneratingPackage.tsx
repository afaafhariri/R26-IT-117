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
    <section className="cs-panel st-generating">
      <div className="between">
        <span className="eyebrow">Render // design package</span>
        <span className="eyebrow dim">
          {totalDone} / {STAGES.length}
        </span>
      </div>
      <h2>{current < STAGES.length ? STAGES[current].label : 'Finalising…'}</h2>
      <Bar value={totalDone} max={STAGES.length} />

      <ol className="st-checklist">
        {STAGES.map((stage, i) => {
          const isDone = done[i];
          const isCurrent = i === current && !isDone;
          return (
            <li key={i} className={isDone ? 'done' : isCurrent ? 'active' : ''}>
              <span className="mark" aria-hidden>
                {isDone ? <CheckIcon /> : isCurrent ? <span className="pulse" /> : `0${i + 1}`}
              </span>
              <span className="label">{stage.label}</span>
              {isCurrent && <span className="eyebrow">Running</span>}
            </li>
          );
        })}
      </ol>

      <p className="faint" style={{ margin: 0 }}>
        Rendering usually takes 30–90 seconds. Please keep this page open.
      </p>
    </section>
  );
}
