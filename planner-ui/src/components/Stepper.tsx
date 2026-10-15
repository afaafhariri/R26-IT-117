import { useLocation, useNavigate } from 'react-router-dom';
import { furthestStep } from '../state/runStore';
import type { RunState } from '../types';

const STEPS = [
  { n: 1, path: '/step/1', label: 'Design', code: 'C01' },
  { n: 2, path: '/step/2', label: 'Materials & Cost', code: 'C02' },
  { n: 3, path: '/step/3', label: 'Timeline', code: 'C03' },
  { n: 4, path: '/step/4', label: 'Performance', code: 'C04' },
  { n: 5, path: '/review', label: 'Review', code: null },
];

export function Stepper({ run }: { run: RunState }) {
  const nav = useNavigate();
  const { pathname } = useLocation();
  const reachable = furthestStep(run);

  return (
    <nav className="stepper" aria-label="Wizard progress">
      {STEPS.map((s) => {
        const unlocked = s.n <= reachable;
        const current = pathname === s.path;
        const done = s.n < reachable;
        return (
          <button
            key={s.n}
            className={`step-chip${done ? ' done' : ''}`}
            aria-current={current}
            disabled={!unlocked}
            onClick={() => nav(s.path)}
            title={unlocked ? undefined : 'Finish the previous step first'}
          >
            <span className="num">{done ? '✓' : `0${s.n}`}</span>
            {s.label}
            {s.code && <span className="code">({s.code})</span>}
          </button>
        );
      })}
    </nav>
  );
}
