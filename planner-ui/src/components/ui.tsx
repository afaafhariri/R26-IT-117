import type { ReactNode } from 'react';
import { ApiError } from '../api/client';

export const lkr = (n: number | null | undefined, compact = false): string => {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  if (compact && Math.abs(n) >= 1_000_000) return `Rs ${(n / 1_000_000).toFixed(2)}M`;
  return `Rs ${Math.round(n).toLocaleString('en-LK')}`;
};

export const num = (n: number | null | undefined, dp = 1): string =>
  n === null || n === undefined || Number.isNaN(n) ? '—' : n.toFixed(dp);

/** Confidence is reported inconsistently: C03 gives 0–1, C04 gives 0–100.
 *  Normalise so neither renders as "9870%". */
export const pct = (n: number | null | undefined): string => {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${Math.round(n <= 1 ? n * 100 : n)}%`;
};

export const dateStr = (s: string | null | undefined): string => {
  if (!s) return '—';
  const d = new Date(s);
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};

/** Format a BOQ quantity for display.
 *
 *  Two things C02 emits verbatim that do not belong in front of a homeowner:
 *  counts arriving as floats (9.0 doors), and the unit "nr" - trade shorthand
 *  for "number of", which reads as a stray typo outside a bill of quantities.
 *  The item name already says what is being counted, so the unit is dropped. */
export const qtyText = (
  quantity: number | null | undefined,
  unit?: string | null,
): string => {
  if (quantity === null || quantity === undefined || Number.isNaN(quantity)) return '—';
  const n = Number.isInteger(quantity) ? String(quantity) : num(quantity);
  const u = !unit || unit === 'nr' ? '' : unit;
  return u ? `${n} ${u}` : n;
};

/** C02 keys every priced line and material choice by its BOQ *quantity field* -
 *  door_count, roof_area_sqm, rc_columns_m3. Those are storage names: rendered
 *  raw they read as "Door Count" and "Roof Area Sqm", where the trailing token
 *  is a unit masquerading as part of the item name. The unit is already shown
 *  in its own column, so label by the work item and drop it. */
const WORK_ITEM_LABELS: Record<string, string> = {
  foundation_excavation_m3: 'Foundation excavation',
  blinding_concrete_m3: 'Blinding concrete',
  foundation_concrete_m3: 'Foundation concrete',
  rc_columns_m3: 'RC columns',
  rc_slab_m3: 'RC slab',
  external_brickwork_m3: 'External brickwork',
  internal_blockwork_m3: 'Internal blockwork',
  roof_area_sqm: 'Roof covering',
  floor_tile_sqm: 'Floor finish',
  wall_plaster_sqm: 'Wall plaster',
  ceiling_sqm: 'Ceiling',
  door_count: 'Doors',
  window_count: 'Windows',
  paint_sqm: 'Painting',
  electrical_points: 'Electrical points',
  total_plumbing_fixtures: 'Plumbing fixtures',
};

export const workItemLabel = (part: string): string =>
  WORK_ITEM_LABELS[part] ?? titleCase(part);

export const titleCase = (s: string): string =>
  s.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export function Card({
  title,
  subtitle,
  actions,
  children,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="between">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <div className="sub">{subtitle}</div>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Loading({ what = 'Loading' }: { what?: string }) {
  return (
    <div className="loading">
      <span className="spinner" aria-hidden />
      <span>{what}…</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/** Renders backend validation detail, not a generic "something went wrong". */
export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const isApi = error instanceof ApiError;
  const message = isApi ? error.message : error instanceof Error ? error.message : String(error);
  const details = isApi ? error.details : [];
  const where = isApi && error.service ? error.service.toUpperCase() : null;

  return (
    <div className="alert error">
      <div className="between">
        <span className="title">
          {where ? `${where}: ` : ''}
          {message}
        </span>
        {onRetry && (
          <button className="ghost" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
      {details.length > 0 && (
        <ul>
          {details.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'ok' | 'warn' | 'danger' | 'neutral';
  children: ReactNode;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

/** Maps C04's status/alert vocabularies onto badge tones. */
export function toneFor(status: string | null | undefined): 'ok' | 'warn' | 'danger' | 'neutral' {
  const s = (status ?? '').toUpperCase();
  if (['OK', 'ON_TRACK', 'ON TRACK', 'COMPLETED', 'COMPLETE', 'LOW'].includes(s)) return 'ok';
  if (['WARNING', 'AT_RISK', 'AT RISK', 'MEDIUM', 'MODERATE'].includes(s)) return 'warn';
  if (['CRITICAL', 'OVERDUE', 'HIGH', 'SEVERE'].includes(s)) return 'danger';
  return 'neutral';
}

export function Bar({
  value,
  max,
  tone,
  pulse,
}: {
  value: number;
  max: number;
  /** Defaults to the accent colour (score bars etc). Pass to colour-code
   *  fullness, e.g. a budget meter shifting ok → warn → danger. */
  tone?: 'ok' | 'warn' | 'danger';
  /** Draws attention when a hard limit has been exceeded. */
  pulse?: boolean;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const color = tone ? `var(--${tone})` : undefined;
  return (
    <div className={`bar${pulse ? ' pulse' : ''}`}>
      <span style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}
