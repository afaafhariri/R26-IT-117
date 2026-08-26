import { useLocation, useNavigate } from 'react-router-dom';
import { furthestStep } from '../state/runStore';
import type { RunState } from '../types';

const STEPS = [
  { n: 1, path: '/step/1', label: 'Design' },
  { n: 2, path: '/step/2', label: 'Materials & Cost' },
  { n: 3, path: '/step/3', label: 'Timeline' },
  { n: 4, path: '/step/4', label: 'Performance' },
  { n: 5, path: '/review', label: 'Review' },
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
            <span className="num">{done ? '✓' : s.n === 5 ? '★' : s.n}</span>
            {s.label}
          </button>
        );
      })}
    </nav>
  );
}
