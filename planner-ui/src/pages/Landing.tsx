import { Link } from 'react-router-dom';
import { useSession } from '../state/session';
import type { RunState } from '../types';

/* The wizard's front door, built from the Stitch "Landing Page" screen.
 * Everything below step 1 assumes you already know what the four components
 * are and why they run in that order - this page is where that is explained,
 * so it stays deliberately free of live data. Where the design called for
 * figures, they are either facts about the pipeline or labelled samples from
 * a real C02 run, never invented benchmarks. */

const STAGES = [
  {
    id: 'c01',
    n: '01',
    name: 'Cadastral deed ingestion',
    icon: 'scan',
    blurb:
      'EasyOCR and a SpaCy NER model trained on Sri Lankan deed formats read the survey plan, parse SLD99 boundary coordinates and resolve the buildable zone.',
    out: 'Floor plan + building specification',
  },
  {
    id: 'c02',
    n: '02',
    name: 'Cost & uncertainty',
    icon: 'sigma',
    blurb:
      'Measures a bill of quantities off the design, prices it at ICTAD rates escalated to your start date, and wraps the total in a conformally calibrated XGBoost band.',
    out: 'Priced BOQ + 90% band',
  },
  {
    id: 'c03',
    n: '03',
    name: 'Programme & critical path',
    icon: 'path',
    blurb:
      'XGBoost predicts each of eleven phase durations from the costed quantities; a PyTorch LSTM checks the total. The phases are sequenced into a Gantt with its critical path.',
    out: 'Gantt + critical path',
  },
  {
    id: 'c04',
    n: '04',
    name: 'Site telemetry & delay risk',
    icon: 'signal',
    blurb:
      'Progress entries become a Schedule Performance Index. When a phase slips, an XGBoost model scores the delay and FAISS retrieves comparable past cases.',
    out: 'SPI + delay alerts',
  },
] as const;

/** A real C02 run: 2 storeys, 240 m², mid grade, coastal Galle (the step-1 sample). */
const SAMPLE_SPREAD = [
  { name: 'Structure (frame, masonry, roof, steel)', lkr: 10_420_056, tone: 'var(--ink)' },
  { name: 'Finishes (floors, plaster, doors, paint)', lkr: 3_945_711, tone: 'var(--terra)' },
  { name: 'Services (electrical, plumbing)', lkr: 471_828, tone: 'var(--accent)' },
];
const SAMPLE_DIRECT = SAMPLE_SPREAD.reduce((a, b) => a + b.lkr, 0);
const SAMPLE_TOTAL = 21_357_668;

const LEDGER = [
  ['C01 · Survey deed', 'EasyOCR + SpaCy NER, CNN plan classifier', 'NBC setback & building-coverage rules per district', 'Floor plan options, building specification'],
  ['C02 · Cost', 'XGBoost quantile regression + SHAP', 'ICTAD unit rates, escalated to the target date', 'Priced BOQ, 50% / 90% bands, budget figure'],
  ['C03 · Programme', 'XGBoost phase model, PyTorch LSTM total', 'Precedence-ordered phase network', 'Gantt, milestones, critical path'],
  ['C04 · Site', 'XGBoost delay model, FAISS, Gemini', 'Schedule Performance Index (SPI)', 'Delay risk, similar cases, actions'],
];

export function Landing({ run }: { run: RunState }) {
  const { user } = useSession();
  const resumable = !!run.step1?.buildingSchema;
  const startLabel = resumable ? 'Continue your plan' : 'Start a new plan';

  return (
    <div className="landing">
      <div className="lp-ticker">
        <div className="lp-inner">
          <span>R26-IT-117 core pipeline</span>
          <span>ICTAD 2024-Q4 base rates</span>
          <span>NBC setback validator</span>
          <span>SLD99 cadastral coordinates</span>
        </div>
      </div>

      <section className="lp-hero">
        <div className="lp-inner">
          <div>
            <span className="eyebrow square">Parametric architecture &amp; civil planning platform</span>
            <h1>AI-powered architecture &amp; residential construction for Sri Lanka</h1>
            <div className="lp-rule" />
            <p className="lp-lede">
              One pass from a land deed to a site you can monitor: a compliant floor plan, a priced
              bill of quantities with a calibrated cost range, a critical-path programme and live
              delay prediction. Four components, each building on the last.
            </p>

            <div className="lp-metrics">
              <div>
                <span className="eyebrow dim">Pipeline</span>
                <div className="v">4 engines</div>
                <div className="h">C01 → C04, chained</div>
              </div>
              <div>
                <span className="eyebrow dim">Cost range</span>
                <div className="v terra">90%</div>
                <div className="h">Conformally calibrated</div>
              </div>
              <div>
                <span className="eyebrow dim">Programme</span>
                <div className="v">11 phases</div>
                <div className="h">XGBoost + LSTM</div>
              </div>
            </div>

            <div className="btn-row">
              <Link to="/step/1" className="btn primary lg">
                {startLabel} <Arrow />
              </Link>
              {resumable && user ? (
                <Link to="/review" className="btn lg">
                  View the summary
                </Link>
              ) : (
                !user && (
                  <Link to="/signup" className="btn lg">
                    Create account
                  </Link>
                )
              )}
            </div>
            <p className="lp-note">// No cadastral plan handy? Step one can load sample data.</p>
          </div>

          <figure className="lp-schematic" aria-label="Illustration of a setback solve">
            <header>
              <span className="eyebrow dim">Schematic: cadastral setback solve</span>
              <span className="chip">Illustrative</span>
            </header>
            <ParcelSchematic />
            <footer>
              <span className="eyebrow dim">Parcel → buildable zone → footprint</span>
              <span className="eyebrow dim">SLD99</span>
            </footer>
          </figure>
        </div>
      </section>

      <section className="lp-section" id="pipeline">
        <div className="lp-inner">
          <div className="lp-head">
            <div>
              <span className="eyebrow">Algorithmic lifecycle</span>
              <h2>Autonomous construction pipeline</h2>
            </div>
            <p>
              Nothing is re-keyed by hand. The chosen design drives the costing, the costed
              quantities drive the programme, and the programme becomes the baseline the site is
              measured against.
            </p>
          </div>

          <div className="lp-stages">
            {STAGES.map((s) => (
              <article className="lp-stage" key={s.n} id={s.id}>
                <div className="top">
                  <span className="eyebrow">{s.n} / Stage</span>
                  <StageIcon kind={s.icon} />
                </div>
                <h3>{s.name}</h3>
                <p>{s.blurb}</p>
                <div className="lp-out">Output: {s.out}</div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-section alt">
        <div className="lp-inner">
          <div className="lp-head underline">
            <div>
              <span className="eyebrow">Modular architecture</span>
              <h2>Engineered for exacting practice</h2>
            </div>
          </div>

          <div className="lp-modules">
            <article className="lp-module">
              <div className="top">
                <span className="eyebrow">// Module 01</span>
                <span className="eyebrow dim">CAD &amp; BIM engine</span>
              </div>
              <h3>Architectural generative solver</h3>
              <p>
                Turns an irregular survey plan into floor plans that fit the district's buildable
                zone, so the design starts compliant instead of being checked afterwards.
              </p>
              <ul className="lp-checks">
                <li>Boundary extraction from the uploaded deed via OCR</li>
                <li>NBC setback and building-coverage rules applied per district</li>
                <li>Several plan options generated, scored, and one handed to costing</li>
              </ul>
              <div className="lp-viz">
                <div className="between">
                  <span className="eyebrow dim">Plan option</span>
                  <span className="chip">Illustrative</span>
                </div>
                <MiniPlan />
              </div>
            </article>

            <article className="lp-module">
              <div className="top">
                <span className="eyebrow">// Module 02</span>
                <span className="eyebrow dim">Quantile ML</span>
              </div>
              <h3>Conformal cost &amp; SHAP analysis</h3>
              <p>
                Every rupee traces back to a measured quantity and a unit rate. The model then says
                how far the real figure could land from it, and why.
              </p>
              <ul className="lp-checks">
                <li>A narrow 50% likely range, a 90% band and a one-sided budget figure</li>
                <li>SHAP attributions name the features that moved the estimate</li>
                <li>Swap materials per work item and the BOQ re-prices instantly</li>
              </ul>
              <div className="lp-viz">
                <div className="between">
                  <span className="eyebrow dim">Direct cost spread · sample run</span>
                  <span className="eyebrow">Rs {(SAMPLE_TOTAL / 1e6).toFixed(2)}M total</span>
                </div>
                <div className="lp-spread">
                  {SAMPLE_SPREAD.map((t) => (
                    <div key={t.name}>
                      <div className="row-l">
                        <span>{t.name}</span>
                        <span className="tnum">
                          Rs {(t.lkr / 1e6).toFixed(2)}M ({Math.round((t.lkr / SAMPLE_DIRECT) * 100)}%)
                        </span>
                      </div>
                      <div className="track">
                        <span style={{ width: `${(t.lkr / SAMPLE_DIRECT) * 100}%`, background: t.tone }} />
                      </div>
                    </div>
                  ))}
                </div>
                <p className="faint" style={{ margin: '0.75rem 0 0' }}>
                  2 storeys · 240 m² · mid grade · coastal Galle
                </p>
              </div>
            </article>

            <article className="lp-module">
              <div className="top">
                <span className="eyebrow">// Module 03</span>
                <span className="eyebrow dim">Neural scheduling</span>
              </div>
              <h3>Critical path &amp; LSTM network</h3>
              <p>
                Phase durations are predicted from the costed quantities rather than guessed from
                floor area, then sequenced so you can see which tasks actually drive the end date.
              </p>
              <ul className="lp-checks">
                <li>XGBoost per-phase durations with a Random Forest fallback</li>
                <li>PyTorch LSTM predicts the total from the phase sequence</li>
                <li>Milestones, dependencies and resource allocation per phase</li>
              </ul>
              <div className="lp-viz">
                <div className="between">
                  <span className="eyebrow dim">Critical path network</span>
                  <span className="chip">Illustrative</span>
                </div>
                <div className="lp-cpm">
                  {[
                    ['Substructure', 0, 22, 'var(--ink)', 'CP'],
                    ['RC frame', 18, 34, 'var(--terra)', 'CP'],
                    ['Masonry', 40, 26, 'var(--ink)', 'CP'],
                    ['Roofing', 58, 16, 'var(--accent)', ''],
                    ['Finishes', 66, 34, 'var(--ink)', 'CP'],
                  ].map(([name, left, width, tone, tag]) => (
                    <div className="r" key={name as string}>
                      <span>{name}</span>
                      <div className="t">
                        <span style={{ left: `${left}%`, width: `${width}%`, background: tone as string }}>
                          {tag}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </article>

            <article className="lp-module">
              <div className="top">
                <span className="eyebrow">// Module 04</span>
                <span className="eyebrow dim">Site telemetry &amp; AI</span>
              </div>
              <h3>SPI telemetry &amp; delay directives</h3>
              <p>
                Site managers record progress per phase. The platform scores schedule performance
                and, when a phase falls behind, predicts the delay and suggests what to do about it.
              </p>
              <ul className="lp-checks">
                <li>Schedule Performance Index with warning and critical thresholds</li>
                <li>Live district weather fed into the delay model</li>
                <li>Similar historical cases retrieved, with Gemini-drafted corrective actions</li>
              </ul>
              <div className="lp-viz">
                <div className="between">
                  <span className="eyebrow dim">Delay alert</span>
                  <span className="chip critical">SPI below threshold</span>
                </div>
                <div className="lp-dispatch">
                  <strong>Example: masonry phase behind plan</strong>
                  <p>
                    Delay risk scored from SPI, labour, material supply and weather; comparable
                    cases and recommended actions are shown alongside.
                  </p>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section className="lp-section">
        <div className="lp-inner">
          <div className="lp-principles">
            <article className="lp-principle">
              <PrincipleArt kind="climate" />
              <span className="eyebrow">Local intelligence</span>
              <h3>Built for Sri Lankan sites</h3>
              <p>
                District rules, ICTAD rates, coastal exposure and terrain all feed the numbers, and
                the delay model is trained on local project records.
              </p>
            </article>
            <article className="lp-principle">
              <PrincipleArt kind="sync" />
              <span className="eyebrow">Field execution</span>
              <h3>One plan, every role</h3>
              <p>
                The same run carries the design, the bill of quantities and the programme, so the
                architect, the QS and the site manager work from one source.
              </p>
            </article>
            <article className="lp-principle">
              <PrincipleArt kind="form" />
              <span className="eyebrow">Bauhaus discipline</span>
              <h3>Form follows performance</h3>
              <p>
                Explainable rather than a black box: every estimate ships with its drivers, and
                every date with the tasks that set it.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="lp-section alt" id="ledger">
        <div className="lp-inner">
          <div className="lp-head">
            <div>
              <span className="eyebrow">Under the hood</span>
              <h2>Core specification ledger</h2>
            </div>
          </div>
          <div className="lp-ledger">
            <table>
              <thead>
                <tr>
                  <th>Pipeline dimension</th>
                  <th>Underlying engine / model</th>
                  <th>Regulatory or method basis</th>
                  <th>Output</th>
                </tr>
              </thead>
              <tbody>
                {LEDGER.map(([dim, engine, basis, output]) => (
                  <tr key={dim}>
                    <td>{dim}</td>
                    <td>{engine}</td>
                    <td>{basis}</td>
                    <td>{output}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="lp-cta">
        <div className="lp-inner">
          <div>
            <span className="eyebrow square">For architects, contractors &amp; quantity surveyors</span>
            <h2>Initiate your project specification</h2>
            <p>
              Upload a Sri Lankan cadastral survey plan and get a compliant floor plan, a priced bill
              of quantities and a critical-path programme, ready to track on site.
            </p>
          </div>
          <div className="stack">
            {user ? (
              <>
                <Link to="/step/1" className="btn accent lg">
                  {startLabel} <Arrow />
                </Link>
                {resumable && (
                  <Link to="/review" className="btn on-dark lg">
                    View the summary
                  </Link>
                )}
              </>
            ) : (
              <>
                <Link to="/login" className="btn accent lg">
                  Access the planner (sign in)
                </Link>
                <Link to="/signup" className="btn on-dark lg">
                  Register a workspace (sign up)
                </Link>
              </>
            )}
            <span className="fine">Sample data available at step one — no survey plan required</span>
          </div>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-inner">
          <nav aria-label="Quick links">
            <span>R26 quick links:</span>
            <a href="#c01">Architecture</a>
            <a href="#c02">Cost estimation</a>
            <a href="#c03">Timeline</a>
            <a href="#c04">Site performance</a>
            <a href="#ledger">Specification</a>
          </nav>
          <span>© 2026 R26-IT-117 construction planner</span>
        </div>
      </footer>
    </div>
  );
}

function Arrow() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
      <path d="M2 8h11M9 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function StageIcon({ kind }: { kind: (typeof STAGES)[number]['icon'] }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.5 };
  return (
    <svg viewBox="0 0 20 20" aria-hidden>
      {kind === 'scan' && (
        <>
          <path d="M2 6V2h4M14 2h4v4M18 14v4h-4M6 18H2v-4" {...common} />
          <path d="M6 7h8M6 10h8M6 13h5" {...common} />
        </>
      )}
      {kind === 'sigma' && <path d="M15 3H5l6 7-6 7h10" {...common} />}
      {kind === 'path' && (
        <>
          <circle cx="4" cy="15" r="2" {...common} />
          <circle cx="16" cy="5" r="2" {...common} />
          <path d="M6 15h4V5h4" {...common} />
        </>
      )}
      {kind === 'signal' && (
        <>
          <circle cx="10" cy="10" r="1.6" fill="currentColor" />
          <path d="M6.5 13.5a5 5 0 0 1 0-7M13.5 6.5a5 5 0 0 1 0 7M4 16a8.5 8.5 0 0 1 0-12M16 4a8.5 8.5 0 0 1 0 12" {...common} />
        </>
      )}
    </svg>
  );
}

/** Irregular parcel, its setback offset, and a footprint inside it. */
function ParcelSchematic() {
  return (
    <svg viewBox="0 0 480 400" role="img" aria-label="Irregular parcel with setback line and building footprint">
      <defs>
        <pattern id="lp-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" fill="none" stroke="var(--border)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="480" height="400" fill="url(#lp-grid)" />
      {/* Survey boundary */}
      <polygon points="60,70 400,40 440,330 90,360" fill="none" stroke="currentColor" strokeWidth="1.5" />
      {[[60, 70], [400, 40], [440, 330], [90, 360]].map(([x, y], i) => (
        <rect key={i} x={x - 4} y={y - 4} width="8" height="8" fill="var(--surface-hi)" stroke="currentColor" />
      ))}
      {/* Setback line */}
      <polygon points="100,105 370,82 400,300 122,322" fill="none" stroke="var(--terra)" strokeWidth="1.2" strokeDasharray="6 4" />
      {/* Footprint */}
      <rect x="150" y="130" width="190" height="150" fill="var(--accent-soft)" stroke="currentColor" strokeWidth="1.5" />
      <rect x="150" y="130" width="100" height="85" fill="none" stroke="currentColor" strokeWidth="0.8" />
      <rect x="250" y="130" width="90" height="85" fill="var(--surface-3)" stroke="currentColor" strokeWidth="0.8" />
      <circle cx="245" cy="205" r="34" fill="none" stroke="var(--terra)" strokeWidth="1.2" />
      <line x1="245" y1="160" x2="245" y2="250" stroke="var(--terra)" strokeWidth="0.8" />
      <line x1="200" y1="205" x2="290" y2="205" stroke="var(--terra)" strokeWidth="0.8" />
      {/* Labels */}
      <g fill="var(--text-dim)" fontFamily="Space Grotesk, sans-serif" fontSize="10" letterSpacing="0.5">
        <text x="70" y="62">LOT BOUNDARY (SURVEY)</text>
        <text x="110" y="98" fill="var(--terra)">NBC SETBACK LINE</text>
        <text x="156" y="296">FOOTPRINT</text>
        <text x="300" y="352">FRONTAGE · ROAD</text>
      </g>
      {/* Dimension */}
      <line x1="150" y1="300" x2="340" y2="300" stroke="currentColor" strokeWidth="0.8" />
      <line x1="150" y1="294" x2="150" y2="306" stroke="currentColor" strokeWidth="0.8" />
      <line x1="340" y1="294" x2="340" y2="306" stroke="currentColor" strokeWidth="0.8" />
    </svg>
  );
}

function MiniPlan() {
  return (
    <svg viewBox="0 0 420 150" role="img" aria-label="Simplified floor plan">
      <g fill="none" stroke="currentColor">
        <rect x="10" y="10" width="250" height="130" strokeWidth="2" />
        <line x1="110" y1="10" x2="110" y2="90" strokeWidth="1" />
        <line x1="10" y1="90" x2="180" y2="90" strokeWidth="1" />
        <line x1="180" y1="10" x2="180" y2="140" strokeWidth="1" />
        <path d="M110 70a20 20 0 0 1 20 20" strokeWidth="0.8" />
        <path d="M180 110a20 20 0 0 1 20-20" strokeWidth="0.8" />
      </g>
      <g fill="var(--text-dim)" fontFamily="Space Grotesk, sans-serif" fontSize="9" letterSpacing="0.5">
        <text x="22" y="30">BED 1</text>
        <text x="122" y="30">BATH</text>
        <text x="192" y="30">LIVING</text>
        <text x="22" y="110">KITCHEN</text>
      </g>
      {/* Elevation */}
      <g fill="none" stroke="currentColor" strokeWidth="1.2">
        <path d="M290 140V80l55-40 55 40v60Z" />
        <rect x="318" y="100" width="20" height="40" />
        <rect x="355" y="92" width="26" height="20" />
      </g>
      <line x1="280" y1="140" x2="412" y2="140" stroke="var(--terra)" strokeWidth="1.5" />
    </svg>
  );
}

function PrincipleArt({ kind }: { kind: 'climate' | 'sync' | 'form' }) {
  return (
    <svg viewBox="0 0 400 300" aria-hidden>
      {kind === 'climate' && (
        <>
          {Array.from({ length: 9 }, (_, i) => (
            <rect key={i} x={70 + i * 30} y="60" width="16" height="180" fill={i % 3 === 1 ? 'var(--terra)' : 'var(--surface-3)'} />
          ))}
          <line x1="40" y1="240" x2="360" y2="240" stroke="var(--ink)" strokeWidth="3" />
        </>
      )}
      {kind === 'sync' && (
        <>
          <rect x="70" y="70" width="120" height="160" fill="none" stroke="var(--ink)" strokeWidth="2" />
          <rect x="210" y="70" width="120" height="160" fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth="2" />
          <line x1="190" y1="150" x2="210" y2="150" stroke="var(--terra)" strokeWidth="3" />
          {[100, 125, 150, 175].map((y) => (
            <line key={y} x1="90" y1={y} x2="170" y2={y} stroke="var(--border-strong)" strokeWidth="6" />
          ))}
          <path d="M230 200l25-40 25 20 30-50" fill="none" stroke="var(--accent)" strokeWidth="2" />
        </>
      )}
      {kind === 'form' && (
        <>
          <rect x="80" y="70" width="140" height="140" fill="var(--ink)" />
          <circle cx="250" cy="150" r="70" fill="var(--terra)" opacity="0.9" />
          <polygon points="200,240 320,240 260,140" fill="var(--ochre)" opacity="0.9" />
        </>
      )}
    </svg>
  );
}
