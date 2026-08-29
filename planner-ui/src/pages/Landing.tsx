import { Link } from 'react-router-dom';
import type { RunState } from '../types';

/* The wizard's front door. Everything below step 1 assumes you already know
 * what the four components are and why they run in that order - this page is
 * where that is explained, so it stays deliberately free of live data. */

const PIPELINE = [
  {
    n: '01',
    name: 'Architecture',
    takes: 'Cadastral plan',
    gives: 'Building schema',
    blurb:
      'Reads the deed, applies NBC setback and building-coverage rules for the district, and generates floor plan options that fit the buildable zone.',
    port: '8001',
  },
  {
    n: '02',
    name: 'Cost Estimation',
    takes: 'Building schema',
    gives: 'Priced bill of quantities',
    blurb:
      'Measures quantities off the design, prices them against ICTAD rates, then adds risk contingency and mark-ups. Every figure traces back to a line item.',
    port: '8002',
  },
  {
    n: '03',
    name: 'Timeline',
    takes: 'Cost estimate',
    gives: 'Critical-path programme',
    blurb:
      'Predicts how long each of eleven construction phases takes from the measured quantities, then sequences them into a Gantt chart with a critical path.',
    port: '8000',
  },
  {
    n: '04',
    name: 'Performance',
    takes: 'Planned programme',
    gives: 'Delay risk & alerts',
    blurb:
      'Tracks actual progress against the plan, scores schedule performance, and predicts delay risk using live site weather and comparable past cases.',
    port: '5004',
  },
];

const OUTPUTS = [
  ['Floor plans', 'Compliant layouts generated from your land, not a template.'],
  ['Costed BOQ', 'Quantities, unit rates and line costs — printable as a PDF.'],
  ['Programme', 'Phase durations, milestones and the tasks that drive the end date.'],
  ['Delay alerts', 'Early warning when a phase slips, with corrective actions.'],
];

export function Landing({ run }: { run: RunState }) {
  const resumable = !!run.step1?.buildingSchema;

  return (
    <div className="landing">
      <section className="hero">
        <span className="eyebrow">R26-IT-117 · Research Project</span>
        <h1>
          From the land deed to the handover,
          <br />
          planned in one pass.
        </h1>
        <p className="lede">
          Upload a Sri Lankan cadastral plan and get a compliant floor plan, a priced bill of
          quantities, a critical-path programme and live delay monitoring — four AI components
          handing off to each other, each one building on the last.
        </p>
        <div className="row hero-cta">
          <Link to="/step/1">
            <button className="primary lg">
              {resumable ? 'Continue your plan' : 'Start a new plan'} →
            </button>
          </Link>
          {resumable && (
            <Link to="/review">
              <button className="lg">View the summary</button>
            </Link>
          )}
        </div>
        <p className="faint hero-note">
          No cadastral plan handy? Step one can load sample data instead.
        </p>
      </section>

      <section className="landing-section">
        <h2>How it works</h2>
        <p className="muted section-lede">
          Each component consumes the one before it. Nothing is re-keyed by hand — the building
          schema drives the costing, the costed quantities drive the programme, and the programme
          becomes the baseline the site is measured against.
        </p>

        <div className="pipeline">
          {PIPELINE.map((c, i) => (
            <article className="pipe-card" key={c.n}>
              <header>
                <span className="pipe-n">{c.n}</span>
                <h3>{c.name}</h3>
              </header>
              <p className="pipe-flow">
                <span className="faint">{c.takes}</span>
                <span className="pipe-arrow" aria-hidden>
                  →
                </span>
                <strong>{c.gives}</strong>
              </p>
              <p className="pipe-blurb">{c.blurb}</p>
              <span className="pipe-port mono">:{c.port}</span>
              {i < PIPELINE.length - 1 && (
                <span className="pipe-link" aria-hidden>
                  →
                </span>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2>What you end up with</h2>
        <div className="grid cols-4">
          {OUTPUTS.map(([title, desc]) => (
            <div className="stat" key={title}>
              <div className="value out-title">{title}</div>
              <div className="hint">{desc}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <h2>Under the hood</h2>
        <div className="grid cols-3">
          <div className="card">
            <h3>Trained on local data</h3>
            <p className="muted">
              Costs are priced from ICTAD/CIDA schedules and adjusted for district, terrain and
              coastal exposure. Delay prediction is trained on Sri Lankan project records.
            </p>
          </div>
          <div className="card">
            <h3>Explainable, not a black box</h3>
            <p className="muted">
              Every estimate ships with SHAP attributions naming the drivers behind the number, and
              the full bill of quantities behind the total.
            </p>
          </div>
          <div className="card">
            <h3>Grounded in past projects</h3>
            <p className="muted">
              When a delay is predicted, the system retrieves comparable cases from a library of
              real construction delays and what resolved them.
            </p>
          </div>
        </div>
      </section>

      <section className="cta-band">
        <div>
          <h2>Ready to plan?</h2>
          <p className="muted">Start with a cadastral plan, or try it with sample data.</p>
        </div>
        <Link to="/step/1">
          <button className="primary lg">
            {resumable ? 'Continue your plan' : 'Start a new plan'} →
          </button>
        </Link>
      </section>
    </div>
  );
}
