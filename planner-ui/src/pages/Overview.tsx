import { Link } from 'react-router-dom';
import { furthestStep } from '../state/runStore';
import type { RunState } from '../types';

/* The Stitch "Architecture & Pipeline Overview" screen, minus its internals:
 * the design also showed a JSON data contract, service ports and a service
 * health board, which describe the deployment rather than the product and
 * are deliberately left out. The rule tables mirror C01's NBC constraint
 * engine, and every research figure is one reported in a component README. */

const MATRIX = [
  {
    n: '01',
    name: 'Architectural planning',
    tag: 'Component C01 // synthesis',
    takes: 'Cadastral survey plan (PDF or image)',
    gives: 'Floor plan options and a building specification',
    steps: [
      'Deed text read by OCR; lot details extracted by a custom entity model',
      'Plot boundary and SLD99 coordinates recovered from the drawing',
      'NBC setbacks and coverage applied to find the buildable zone',
      'Three layouts generated at increasing creativity, then validated',
      'Each layout scored on space use, light, adjacency and ventilation',
      'Renders, 2D blueprint and 3D views produced for the chosen plan',
    ],
    note: 'Starts every plan',
    step: '/step/1',
  },
  {
    n: '02',
    name: 'Cost estimation',
    tag: 'Component C02 // conformal ML',
    takes: 'Building specification',
    gives: 'Priced bill of quantities with calibrated cost bands',
    steps: [
      'Bill of quantities measured from the design geometry',
      'ICTAD unit rates escalated to the target date, adjusted by district',
      'XGBoost quantile model with conformal calibration (50% and 90% bands)',
      'Site-risk contingency and mark-ups, with SHAP cost drivers',
    ],
    note: '90% band: 90.0% empirical coverage',
    step: '/step/2',
  },
  {
    n: '03',
    name: 'Timeline & critical path',
    tag: 'Component C03 // topological CPM',
    takes: 'Costed quantities and labour',
    gives: 'Phase programme, Gantt and critical path',
    steps: [
      'XGBoost predicts each phase duration from the costed quantities',
      'PyTorch LSTM predicts the total from the phase sequence',
      'Phases ordered by dependency; critical chain identified',
      'Planned baseline prepared for site monitoring',
    ],
    note: 'Phase model: 5.48% MAPE',
    step: '/step/3',
  },
  {
    n: '04',
    name: 'Site delay mitigation',
    tag: 'Component C04 // RAG + SPI',
    takes: 'Planned baseline and site progress',
    gives: 'SPI alerts, delay risk and corrective actions',
    steps: [
      'Schedule Performance Index with 0.85 warning and 0.70 critical thresholds',
      'XGBoost delay model scores risk and expected slippage',
      'Similar past delays retrieved from 192 Sri Lankan cases',
      'Gemini drafts corrective actions grounded in those cases',
    ],
    note: 'Live district weather in the model',
    step: '/step/4',
  },
];

/** NBCConstraintEngine.SETBACKS, in metres. */
const SETBACKS = [
  ['National road', 4.5, 1.5, 1.0],
  ['Provincial road', 3.0, 1.5, 1.0],
  ['Local road', 1.5, 1.5, 1.0],
  ['Lane', 1.0, 1.5, 0.5],
] as const;

const COVERAGE = [
  ['Coastal plots', '40%', 'Plots in Ampara, Batticaloa, Colombo, Galle, Gampaha, Hambantota, Jaffna, Kalutara, Kilinochchi, Mannar, Matara, Puttalam, Trincomalee'],
  ['Colombo & Gampaha (inland plots)', '65%', 'Dense urban districts'],
  ['All other districts', '50%', 'Default residential coverage'],
] as const;

const METRICS = [
  ['C02 cost band', '90.0%', 'Empirical coverage of the 90% band'],
  ['C02 budget figure', '94.0%', 'Projects at or below the one-sided 90% figure'],
  ['C03 phase model', '5.48%', 'Mean absolute percentage error'],
  ['C03 sequence LSTM', '0.978', 'R² on project totals'],
  ['C04 case library', '192', 'Historical Sri Lankan delay cases'],
];

export function Overview({ run }: { run: RunState }) {
  const reached = furthestStep(run);
  const launch = [
    { code: 'C01 · Stage 1', title: 'Upload cadastral plan', blurb: 'Read the survey plan and find the buildable zone, then generate plan options.', to: '/step/1', icon: 'doc' },
    { code: 'C02 · Quantile', title: 'Cost calibration', blurb: 'Price the bill of quantities and see the 50% and 90% cost bands.', to: '/step/2', icon: 'grid' },
    { code: 'C03 · CPM', title: 'Timeline & Gantt', blurb: 'Predict phase durations and the critical path from the costed design.', to: '/step/3', icon: 'path' },
    { code: 'C04 · SPI', title: 'Site delay monitor', blurb: 'Record progress, score SPI and get delay predictions with actions.', to: '/step/4', icon: 'gauge' },
  ];

  return (
    <div className="landing">
      <div className="lp-ticker">
        <div className="lp-inner">
          <span>Research project R26-IT-117</span>
          <span>National Building Code (NBC) automation</span>
          <span>ICTAD rate matrix 2024-Q4</span>
          <span>SLD99 survey coordinates</span>
        </div>
      </div>

      <section className="lp-hero">
        <div className="lp-inner">
          <div>
            <span className="eyebrow square">Research project R26-IT-117 // Sri Lankan residential housing</span>
            <h1 className="ov-title">AI-driven construction planning &amp; execution engine</h1>
            <p className="lp-lede">
              End-to-end architectural synthesis, ICTAD rate-calibrated cost estimation,
              critical-path timeline prediction and live SPI delay mitigation, built specifically
              for Sri Lankan residential construction.
            </p>
            <div className="ov-stats">
              <div style={{ borderBottomColor: 'var(--terra)' }}>
                <span className="eyebrow dim">Components</span>
                <b>04 engines</b>
                <small>Chained C01 → C04</small>
              </div>
              <div style={{ borderBottomColor: 'var(--ochre)' }}>
                <span className="eyebrow dim">Zoning engine</span>
                <b>NBC &amp; BCR</b>
                <small>Setbacks by road, coverage by district</small>
              </div>
              <div style={{ borderBottomColor: 'var(--accent)' }}>
                <span className="eyebrow dim">Quantile ML</span>
                <b>90% band</b>
                <small>Conformally calibrated</small>
              </div>
              <div style={{ borderBottomColor: 'var(--ink)' }}>
                <span className="eyebrow dim">Cadastral AI</span>
                <b>SLD99</b>
                <small>Survey coordinates read off the deed</small>
              </div>
            </div>
          </div>
          <figure className="ov-figure" aria-label="The four components as Bauhaus forms">
            <div className="between">
              <span className="eyebrow">Figure 01 // the pipeline</span>
              <span className="eyebrow" style={{ color: 'var(--ochre)' }}>C01 → C04</span>
            </div>
            <svg viewBox="0 0 320 300" aria-hidden>
              <rect x="70" y="60" width="90" height="90" fill="var(--terra)" />
              <circle cx="210" cy="105" r="48" fill="var(--ochre)" />
              <polygon points="80,250 250,250 165,160" fill="var(--accent)" />
              <line x1="70" y1="40" x2="260" y2="270" stroke="var(--on-ink)" strokeWidth="3" />
              <g fontFamily="Space Grotesk, sans-serif" fontSize="9" letterSpacing="0.5" fill="var(--on-ink)">
                <text x="78" y="76">C01 · PLAN</text>
                <text x="190" y="108">C02 · COST</text>
                <text x="128" y="236">C03 / C04 · TIME</text>
              </g>
            </svg>
            <dl>
              <dt>Input</dt>
              <dd>Cadastral survey plan</dd>
              <dt>Output</dt>
              <dd>Design, BOQ, programme, site alerts</dd>
              <dt>Coastal rule</dt>
              <dd className="terra">40% coverage cap</dd>
            </dl>
          </figure>
        </div>
      </section>

      <section className="lp-section">
        <div className="lp-inner">
          <div className="lp-head">
            <div>
              <span className="eyebrow">Engine architecture</span>
              <h2>Modular pipeline matrix [C01 — C04]</h2>
            </div>
            <p>Each stage consumes the one before it, from the deed scan to site-level delay mitigation.</p>
          </div>
          <div className="ov-matrix">
            {MATRIX.map((m) => (
              <article key={m.n}>
                <div className="between">
                  <span className="ov-n">{m.n}</span>
                  <span className="chip">{m.tag.split(' // ')[0].replace('Component ', '')}</span>
                </div>
                <h3>{m.name}</h3>
                <span className="eyebrow dim">{m.tag}</span>
                <div className="ov-io">
                  <span>
                    <b>In:</b> {m.takes}
                  </span>
                  <span className="terra">
                    <b>Out:</b> {m.gives}
                  </span>
                </div>
                <ol>
                  {m.steps.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
                <div className="between ov-foot">
                  <span className="faint">{m.note}</span>
                  <Link to={m.step} className="auth-link">
                    Open stage →
                  </Link>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-section alt" id="rules">
        <div className="lp-inner ov-rules">
          <div>
            <span className="eyebrow">Regulatory lookup</span>
            <h2>NBC zoning &amp; setback calibration</h2>
            <p className="faint">
              The rules C01 applies when it carves the buildable zone out of a plot. Setbacks follow
              the road the plot fronts; coverage follows the district.
            </p>
            <div className="lp-ledger" style={{ marginTop: '1rem' }}>
              <table>
                <thead>
                  <tr>
                    <th>Road access</th>
                    <th className="num">Front (m)</th>
                    <th className="num">Rear (m)</th>
                    <th className="num">Side (m)</th>
                  </tr>
                </thead>
                <tbody>
                  {SETBACKS.map(([road, f, r, s]) => (
                    <tr key={road}>
                      <td>{road}</td>
                      <td className="num">{f.toFixed(2)}</td>
                      <td className="num">{r.toFixed(2)}</td>
                      <td className="num">{s.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            <div className="lp-ledger">
              <table>
                <thead>
                  <tr>
                    <th>District type</th>
                    <th className="num">Max BCR</th>
                    <th>Applies to</th>
                  </tr>
                </thead>
                <tbody>
                  {COVERAGE.map(([type, bcr, where]) => (
                    <tr key={type}>
                      <td>{type}</td>
                      <td className="num terra">{bcr}</td>
                      <td style={{ fontSize: '0.8rem' }}>{where}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="cs-notice" style={{ marginTop: '1rem' }}>
              <svg viewBox="0 0 20 20" aria-hidden>
                <circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <path d="M10 9v5M10 5.8v1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
              </svg>
              <div>
                <b>Floor limits by plot size</b>
                <p>Under 200 m²: one floor. 200–500 m²: two floors. Over 500 m²: three floors.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="lp-section">
        <div className="lp-inner">
          <div className="lp-head">
            <div>
              <span className="eyebrow">Task control room</span>
              <h2>Pipeline action launchpad</h2>
            </div>
            <p>Jump to a stage. Each one unlocks once the stage before it has produced its output.</p>
          </div>
          <div className="ov-launch">
            {launch.map((l, i) => {
              const open = i + 1 <= reached;
              const done = i + 1 < reached;
              return (
                <article key={l.to} className={open ? '' : 'locked'}>
                  <div className="between">
                    <LaunchIcon kind={l.icon} />
                    <span className="eyebrow dim">{l.code}</span>
                  </div>
                  <h3>{l.title}</h3>
                  <p>{l.blurb}</p>
                  {open ? (
                    <Link to={l.to} className="auth-link">
                      {done ? 'Revisit' : 'Launch'} stage 0{i + 1} →
                    </Link>
                  ) : (
                    <span className="eyebrow dim">Finish stage 0{i} first</span>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="lp-section alt">
        <div className="lp-inner ov-metrics">
          <div>
            <span className="eyebrow">Research metrics &amp; reproducibility</span>
            <h3>Validation baselines</h3>
            <p className="faint">Figures reported by each component on its held-out test data.</p>
          </div>
          <div className="ov-metric-chips">
            {METRICS.map(([k, v, h]) => (
              <div key={k} title={h}>
                <span className="eyebrow dim">{k}</span>
                <b>{v}</b>
                <small>{h}</small>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-inner">
          <span>National Building Code (NBC) &amp; ICTAD rate schedules</span>
          <span>© 2026 R26-IT-117 construction planner</span>
        </div>
      </footer>
    </div>
  );
}

function LaunchIcon({ kind }: { kind: string }) {
  const c = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.5 };
  return (
    <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden>
      {kind === 'doc' && <path d="M5 2h7l4 4v12H5ZM12 2v4h4M8 11h5M10.5 8.5v5" {...c} />}
      {kind === 'grid' && <path d="M3 3h14v14H3ZM3 8h14M3 13h14M8 3v14M13 3v14" {...c} />}
      {kind === 'path' && <path d="M2 15l5-6 4 3 7-9" {...c} />}
      {kind === 'gauge' && (
        <>
          <path d="M3 14a7 7 0 1 1 14 0" {...c} />
          <path d="M10 14l3.5-4" {...c} />
        </>
      )}
    </svg>
  );
}
