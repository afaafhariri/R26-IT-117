import { useState, type ReactNode } from 'react';
import { ApiError } from '../../api/client';

/* The account pages share the Stitch "Sign In" / "Sign Up" frame: a drafting
 * panel on the left, the form on the right, and a datum line above and below.
 * The gateway only knows email + password (+ remember me), so the design's
 * extra fields - CIDA/IESL numbers, discipline, full name - are not drawn:
 * collecting data the backend would throw away would mislead the user. */

type Aside = 'signin' | 'signup';

export function AuthShell({
  aside = 'signin',
  badge,
  title,
  lede,
  children,
  after,
}: {
  aside?: Aside;
  badge: string;
  title: string;
  lede?: ReactNode;
  children: ReactNode;
  /** Below the form inside the right panel, e.g. the "new here?" callout. */
  after?: ReactNode;
}) {
  return (
    <div className="auth-wrap">
      <div className="auth-datum" aria-hidden>
        <div>
          <span className="eyebrow square">Spec // R26-IT-117</span>
        </div>
        <div>
          <span>Lat: 6.9271° N, 79.8612° E</span>
          <span className="terra">Sri Lanka</span>
        </div>
      </div>

      <div className="auth-box">
        <aside className="auth-aside">{aside === 'signup' ? <SignupAside /> : <SigninAside />}</aside>
        <section className="auth-main">
          <div className="between">
            <span className="chip terra">
              <span className="square-dot" aria-hidden />
              {badge}
            </span>
            <span className="eyebrow dim">R26 Planner</span>
          </div>
          <h1>{title}</h1>
          {lede && <p className="lede">{lede}</p>}
          {children}
          {after}
        </section>
      </div>

      <div className="auth-status">
        <div>
          <span className="dot ok" aria-hidden />
          <span>Secure sign-in</span>
          <span aria-hidden>//</span>
          <span>Your plans stay private to your account</span>
        </div>
        <div>
          <span>© 2026 R26-IT-117</span>
        </div>
      </div>
    </div>
  );
}

function SigninAside() {
  return (
    <>
      <div>
        <span className="auth-stamp">
          <CompassIcon /> R26-IT-117 // Suite
        </span>
        <h2>Civil matrix &amp; parametric cadence</h2>
        <p>
          One workspace for the whole plan: the design, its bill of quantities, the programme and
          the progress recorded on site.
        </p>
        <div className="auth-figure">
          <div className="between">
            <span>SECTION SEC-402</span>
            <span className="terra">Illustrative</span>
          </div>
          <TrussFigure />
          <div className="between">
            <span>Truss · two bays</span>
            <span>Pin / roller</span>
          </div>
        </div>
      </div>
      <div className="auth-protocol">
        <span className="eyebrow dim">
          <CheckIcon /> NBC-LK setback rules
        </span>
        <span className="label-sm" style={{ color: 'var(--text-dim)' }}>
          C01–C04
        </span>
      </div>
    </>
  );
}

function SignupAside() {
  return (
    <>
      <div>
        <span className="eyebrow">Specification block</span>
        <h2 style={{ marginTop: '0.5rem' }}>C01 – C04 engines</h2>
        <p>
          Automated spatial planning, quantity take-off and pricing, programme synthesis and
          site delay monitoring for Sri Lankan residential projects.
        </p>
        <div className="auth-facts">
          <div className="auth-fact">
            <CompassIcon />
            <div>
              <b>Planning rules</b>
              <span>NBC setback and building-coverage limits per district</span>
            </div>
          </div>
          <div className="auth-fact">
            <LedgerIcon />
            <div>
              <b>Rate benchmarking</b>
              <span>ICTAD 2024-Q4 unit rates, escalated to your start date</span>
            </div>
          </div>
          <div className="auth-fact">
            <CheckIcon />
            <div>
              <b>Verified access</b>
              <span>Every account confirms its email before the first sign-in</span>
            </div>
          </div>
        </div>
      </div>
      <div>
        <span className="eyebrow dim">System notice</span>
        <p style={{ marginTop: '0.4rem' }}>
          Your plan is saved in this browser and tied to your account. Signing out clears it from
          this device.
        </p>
      </div>
    </>
  );
}

/** Kept for the secondary account pages (verify, forgot, reset), which only
 *  need a heading, an optional lede and a footer link. */
export function AuthLayout({
  title,
  subtitle,
  footer,
  badge = 'Account',
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  footer?: ReactNode;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <AuthShell
      badge={badge}
      title={title}
      lede={subtitle}
      after={footer && <p className="auth-footer-line">{footer}</p>}
    >
      {children}
    </AuthShell>
  );
}

/** Label row with a right-aligned technical hint, as in the design. */
export function AuthField({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="auth-field">
      <div className="between">
        <label htmlFor={id}>{label}</label>
        {hint && <span className="hint">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

/** Password input with a show/hide toggle. */
export function PasswordInput({
  id,
  value,
  onChange,
  autoComplete,
  minLength,
  placeholder = '••••••••••••',
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
  minLength?: number;
  placeholder?: string;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className="auth-input">
      <input
        id={id}
        type={shown ? 'text' : 'password'}
        autoComplete={autoComplete}
        required
        minLength={minLength}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        aria-label={shown ? 'Hide password' : 'Show password'}
        aria-pressed={shown}
        onClick={() => setShown((s) => !s)}
      >
        <EyeIcon off={shown} />
      </button>
    </div>
  );
}

/** The gateway's own message, without the "AUTH:" prefix ErrorBox would add. */
export function FormError({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  const details = error instanceof ApiError ? error.details : [];
  return (
    <div className="alert error" role="alert">
      {message}
      {details.length > 0 && (
        <ul>
          {details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ArrowIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path d="M2 8h11M9 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden>
      <path d="M1.5 10S4.5 4 10 4s8.5 6 8.5 6-3 6-8.5 6S1.5 10 1.5 10Z" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="10" cy="10" r="2.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      {off && <line x1="3" y1="17" x2="17" y2="3" stroke="currentColor" strokeWidth="1.5" />}
    </svg>
  );
}

function CompassIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden>
      <circle cx="10" cy="3.5" r="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M9 5 4 18M11 5l5 13M6 12.5h8" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function LedgerIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden>
      <rect x="2.5" y="3.5" width="15" height="13" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5.5 8h4M5.5 11h4M5.5 14h2.5M12 9l1.5 1.5L16 8" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden>
      <path d="M10 1.8 12.3 3.5h2.9l.9 2.7 2.3 1.8-.9 2.7.9 2.7-2.3 1.8-.9 2.7h-2.9L10 18.2l-2.3-1.7H4.8l-.9-2.7-2.3-1.8.9-2.7-.9-2.7 2.3-1.8.9-2.7h2.9Z" fill="none" stroke="var(--terra)" strokeWidth="1.3" />
      <path d="m6.8 10 2.2 2.2 4.2-4.4" fill="none" stroke="var(--terra)" strokeWidth="1.5" />
    </svg>
  );
}

function TrussFigure() {
  return (
    <svg viewBox="0 0 240 120" aria-hidden>
      <g stroke="currentColor" fill="none">
        <line x1="10" x2="230" y1="10" y2="10" strokeWidth="0.75" strokeDasharray="2 2" opacity="0.4" />
        <line x1="10" x2="230" y1="60" y2="60" strokeWidth="0.75" strokeDasharray="2 2" opacity="0.4" />
        <line x1="10" x2="230" y1="110" y2="110" strokeWidth="0.75" strokeDasharray="2 2" opacity="0.4" />
        <polygon points="20,100 70,30 120,100" strokeWidth="1.5" />
        <polygon points="120,100 170,30 220,100" strokeWidth="1.5" />
        <line x1="70" x2="170" y1="30" y2="30" strokeWidth="2" />
        <line x1="20" x2="220" y1="100" y2="100" strokeWidth="2" />
      </g>
      <circle cx="70" cy="30" r="3" fill="var(--terra)" />
      <circle cx="170" cy="30" r="3" fill="var(--terra)" />
      <circle cx="120" cy="100" r="3.5" fill="currentColor" />
      <path d="M70 20V5M170 20V5" stroke="var(--terra)" strokeWidth="1.25" />
    </svg>
  );
}
