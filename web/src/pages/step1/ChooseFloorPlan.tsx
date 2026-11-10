import { useState } from 'react';
import { ApiError } from '../../api/client';
import { selectFloorPlan } from '../../api/services';
import type { C01FloorPlanAlternative, C01FullDesignPackage } from '../../types';
import { PlanSchematic } from './PlanSchematic';
import { roomAreaSqm } from './rooms';

const FT = 0.3048;
const SQFT = 0.092903;

/** C01 scores each layout 0–10 on these. */
const METRICS: { key: keyof C01FloorPlanAlternative['scores']; label: string; tone: string }[] = [
  { key: 'space_utilisation', label: 'Space utilisation', tone: 'var(--ink)' },
  { key: 'natural_light', label: 'Natural daylighting', tone: 'var(--ochre)' },
  { key: 'adjacency', label: 'Room adjacency', tone: 'var(--terra)' },
  { key: 'ventilation', label: 'Ventilation', tone: 'var(--accent)' },
];

const VARIANT_BLURB: Record<string, string> = {
  conservative: 'Closest to conventional layouts',
  balanced: 'A middle path between convention and novelty',
  creative: 'Most exploratory arrangement',
};

type Props = {
  jobId: string;
  alternatives: C01FloorPlanAlternative[];
  onGenerating: () => void;
  onSuccess: (pkg: C01FullDesignPackage) => void;
  onError: (msg: string) => void;
  error?: string | null;
};

export function ChooseFloorPlan({ jobId, alternatives, onGenerating, onSuccess, onError, error }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const alt = alternatives.find((a) => a.variant === selected) ?? null;

  const generate = async () => {
    if (!selected) return;
    setLoading(true);
    onGenerating();
    try {
      const pkg = await selectFloorPlan(jobId, selected);
      onSuccess(pkg);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Generation failed.');
      setLoading(false);
    }
  };

  return (
    <>
      <section className="cs-panel">
        <div className="between" style={{ alignItems: 'flex-start' }}>
          <div>
            <h2 style={{ fontSize: '1.4rem' }}>Choose a layout</h2>
            <p className="faint" style={{ margin: '0.35rem 0 0' }}>
              Three layouts generated for your brief, each validated against the buildable zone and
              scored out of 10.
            </p>
          </div>
        </div>
        <div className="st-alts">
          {alternatives.map((a, i) => {
            const isSel = a.variant === selected;
            return (
              <button
                type="button"
                key={a.variant}
                className={`st-alt${isSel ? ' selected' : ''}`}
                aria-pressed={isSel}
                onClick={() => setSelected(a.variant)}
              >
                {isSel && <span className="st-alt-tag">Selected proposal</span>}
                <span className="between">
                  <span className="eyebrow dim">Option 0{i + 1}</span>
                  <span className={`chip${isSel ? ' terra' : ''}`}>{a.scores.overall.toFixed(1)} score</span>
                </span>
                <span className="st-alt-name">{a.variant}</span>
                <span className="st-alt-desc">{a.description || VARIANT_BLURB[a.variant]}</span>
                <span className="between st-alt-foot">
                  <span>Built area: {(a.total_built_area_sqft * SQFT).toFixed(0)} m²</span>
                  <span className={isSel ? 'terra' : ''}>{isSel ? 'Active view' : 'Select →'}</span>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {alt && (
        <>
          <section className="cs-panel">
            <div className="between" style={{ marginBottom: '0.75rem' }}>
              <span className="eyebrow dim">Plan schematic — {alt.variant} option</span>
              <span className={`chip ${alt.validation_passed ? 'nominal' : 'review'}`}>
                {alt.validation_passed
                  ? 'Validation passed'
                  : `${alt.violations.length} issue${alt.violations.length === 1 ? '' : 's'}`}
              </span>
            </div>
            <PlanSchematic key={alt.variant} rooms={alt.rooms} />
          </section>

          <section className="cs-panel">
            <div className="between" style={{ marginBottom: '1rem' }}>
              <span className="eyebrow dim">Multi-metric evaluation ({alt.variant})</span>
              <span className="chip">
                Overall: <b>{alt.scores.overall.toFixed(1)} / 10</b>
              </span>
            </div>
            <div className="st-metrics">
              {METRICS.map((m) => (
                <div key={m.key}>
                  <div className="between">
                    <span className="eyebrow dim">{m.label}</span>
                    <b>{alt.scores[m.key].toFixed(1)}</b>
                  </div>
                  <div className="track">
                    <span style={{ width: `${(alt.scores[m.key] / 10) * 100}%`, background: m.tone }} />
                  </div>
                </div>
              ))}
            </div>

            {!alt.validation_passed && alt.violations.length > 0 && (
              <div className="cs-notice warn" style={{ marginTop: '1rem' }}>
                <svg viewBox="0 0 20 20" aria-hidden>
                  <circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M10 5.5v5.5M10 13.4v1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
                </svg>
                <div>
                  <b>Validation issues</b>
                  <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
                    {alt.violations.map((v, i) => (
                      <li key={i}>
                        <p>{v}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            <div className="table-wrap" style={{ marginTop: '1rem' }}>
              <table className="st-table">
                <thead>
                  <tr>
                    <th>Room</th>
                    <th className="num">Floor</th>
                    <th className="num">Area (m²)</th>
                    <th className="num">Size (m)</th>
                    <th>Window</th>
                    <th>Door</th>
                  </tr>
                </thead>
                <tbody>
                  {alt.rooms.map((r, i) => (
                    <tr key={i}>
                      <td>
                        <b>{r.name}</b>
                      </td>
                      <td className="num">{r.floor ?? 1}</td>
                      <td className="num">{roomAreaSqm(r).toFixed(2)}</td>
                      <td className="num">
                        {(r.width_ft * FT).toFixed(2)} × {(r.length_ft * FT).toFixed(2)}
                      </td>
                      <td>
                        <span className={`chip ${r.has_window ? 'nominal' : ''}`}>{r.has_window ? 'Yes' : 'No'}</span>
                      </td>
                      <td>
                        <span className={`chip ${r.has_door ? 'nominal' : ''}`}>{r.has_door ? 'Yes' : 'No'}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {error && <div className="alert error">Generation failed: {error}</div>}

      <div className="cs-status">
        <div>
          <span className="eyebrow">{alt ? `${alt.variant} option ready` : 'Select a plan option'}</span>
          <p className="faint" style={{ margin: '0.25rem 0 0' }}>
            Approving renders the exterior, interior, 2D blueprint and 3D views. You review them before
            the design goes to cost estimation.
          </p>
        </div>
        <button className="accent" onClick={generate} disabled={!selected || loading}>
          {loading ? (
            <>
              <span className="spinner" aria-hidden /> Generating full design…
            </>
          ) : (
            'Approve plan & generate package →'
          )}
        </button>
      </div>
    </>
  );
}
