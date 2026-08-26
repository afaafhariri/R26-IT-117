import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { Stepper } from './components/Stepper';
import { useRun } from './state/runStore';
import { Step1Design } from './pages/Step1Design';
import { Step2Cost } from './pages/Step2Cost';
import { Step3Timeline } from './pages/Step3Timeline';
import { Step4Performance } from './pages/Step4Performance';
import { Review } from './pages/Review';

export default function App() {
  const { run, update, reset } = useRun();
  const nav = useNavigate();

  const startOver = () => {
    if (!confirm('Clear this run and start over? All saved step output will be lost.')) return;
    reset();
    nav('/step/1');
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          Construction Planner
          <small>R26-IT-117</small>
        </div>
        <div className="topbar-spacer" />
        <span className="faint mono">{run.runId.slice(0, 8)}</span>
        <button className="ghost" onClick={startOver}>
          Start over
        </button>
      </header>

      <Stepper run={run} />

      <main className="container">
        <Routes>
          <Route path="/" element={<Navigate to="/step/1" replace />} />
          <Route path="/step/1" element={<Step1Design run={run} update={update} />} />
          <Route path="/step/2" element={<Step2Cost run={run} update={update} />} />
          <Route path="/step/3" element={<Step3Timeline run={run} update={update} />} />
          <Route path="/step/4" element={<Step4Performance run={run} update={update} />} />
          <Route path="/review" element={<Review run={run} />} />
          <Route path="*" element={<Navigate to="/step/1" replace />} />
        </Routes>
      </main>
    </div>
  );
}
