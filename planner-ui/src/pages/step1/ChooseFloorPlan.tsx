import { useState } from 'react';
import { Bar } from '../../components/ui';
import { ApiError } from '../../api/client';
import { selectFloorPlan } from '../../api/services';
import type { C01FloorPlanAlternative, C01FullDesignPackage } from '../../types';
import { MiniFloorPlan } from './MiniFloorPlan';

function ScoreRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="score-row">
      <span style={{ width: '6.5em' }}>{label}</span>
      <Bar value={value} max={10} />
      <span className="val">{value.toFixed(1)}</span>
    </div>
  );
}

function PlanCard({
  alt,
  selected,
  onSelect,
}: {
  alt: C01FloorPlanAlternative;
  selected: boolean;
  onSelect: () => void;
}) {
  const floors = [...new Set(alt.rooms.map((r) => r.floor ?? 1))].sort();
  return (
    <div className={`plan-card${selected ? ' selected' : ''}`} onClick={onSelect}>
      <div className="between" style={{ marginBottom: '0.6rem' }}>
        <h3 style={{ textTransform: 'capitalize' }}>{alt.variant}</h3>
        <span
          title={alt.validation_passed ? 'Layout passed all checks' : alt.violations.join('\n')}
          className={`badge ${alt.validation_passed ? 'ok' : 'warn'}`}
        >
          {alt.validation_passed ? 'Passed' : `⚠ ${alt.violations.length} issue${alt.violations.length === 1 ? '' : 's'}`}
        </span>
      </div>

      <MiniFloorPlan rooms={alt.rooms} />

      <div className="stack" style={{ gap: '0.3rem', marginTop: '0.7rem' }}>
        <ScoreRow label="Space use" value={alt.scores.space_utilisation} />
        <ScoreRow label="Light" value={alt.scores.natural_light} />
        <ScoreRow label="Adjacency" value={alt.scores.adjacency} />
        <ScoreRow label="Ventilation" value={alt.scores.ventilation} />
        <ScoreRow label="Overall" value={alt.scores.overall} />
      </div>

      <div className="divider" />
      <p className="faint" style={{ marginBottom: '0.4rem' }}>
        {alt.total_built_area_sqft.toFixed(0)} sqft total · {alt.rooms.length} rooms
      </p>
      <div style={{ maxHeight: 140, overflowY: 'auto' }}>
        {floors.map((floorNum) => (
          <div key={floorNum}>
            {floors.length > 1 && (
              <p className="faint" style={{ fontSize: '0.68rem', textTransform: 'uppercase', margin: '0.3rem 0 0.15rem' }}>
                Floor {floorNum}
              </p>
            )}
            {alt.rooms
              .filter((r) => (r.floor ?? 1) === floorNum)
              .map((r, i) => (
                <div key={i} className="between" style={{ fontSize: '0.8rem', padding: '0.1rem 0' }}>
                  <span>{r.name}</span>
                  <span className="faint mono">
                    {r.width_ft.toFixed(0)} × {r.length_ft.toFixed(0)} ft
                  </span>
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

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
    <div className="stack">
      <div>
        <h1>Choose a Floor Plan</h1>
        <p className="muted">Pick one of the three AI-generated alternatives to build your full design package.</p>
      </div>

      <div className="grid cols-3">
        {alternatives.map((alt) => (
          <PlanCard key={alt.variant} alt={alt} selected={selected === alt.variant} onSelect={() => setSelected(alt.variant)} />
        ))}
      </div>

      {error && <div className="alert error">Generation failed: {error}</div>}

      <div className="footer-nav">
        <span />
        <button className="primary" onClick={generate} disabled={!selected || loading}>
          {loading ? (
            <>
              <span className="spinner" aria-hidden /> Generating full design…
            </>
          ) : selected ? (
            `Generate Full Design — ${selected}`
          ) : (
            'Select a plan above'
          )}
        </button>
      </div>
    </div>
  );
}
