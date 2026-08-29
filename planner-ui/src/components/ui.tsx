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
