import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { estimate, fetchMaterials } from '../api/services';
import { Badge, Card, ErrorBox, Loading, lkr, num, qtyText, titleCase, workItemLabel } from '../components/ui';
import type { CostReport, RunState, TradeLine } from '../types';

/* Step 2, built from the Stitch "C02 Conformal Quantile Cost Estimation
 * Breakdown" screen. Every figure on it comes from C02's /estimate response;
 * where the design showed something C02 does not produce (a provincial
 * baseline, model tree depth, a downloadable XLS) it is left out or replaced
 * by the nearest real field. */

/** How much of this item C02 measured off the building schema, e.g. "9 nr" or
 *  "156 m²". Read from trade_breakdown, which carries quantity and unit for
 *  every priced line - so the picker shows what is actually being bought. */
function partQuantity(report: CostReport | undefined, part: string): string | null {
  const line = report?.trade_breakdown?.[part];
  if (!line || typeof line.quantity !== 'number') return null;
  return qtyText(line.quantity, line.unit);
}

/** The same grouping C02's report builder uses for trade_value_breakdown, so
 *  section subtotals here add up to the figures it hands to C03. */
const SECTIONS = [
  {
    key: 'structural',
    code: 'ST',
    title: 'Section 01: Substructure, frame, masonry & roof',
    chip: 'Structural',
    parts: [
      'foundation_excavation_m3',
      'blinding_concrete_m3',
      'foundation_concrete_m3',
      'rc_columns_m3',
      'rc_slab_m3',
      'steel_kg_estimate',
      'external_brickwork_m3',
      'internal_blockwork_m3',
      'roof_area_sqm',
    ],
  },
  {
    key: 'finishes',
    code: 'FN',
    title: 'Section 02: Envelope & architectural finishes',
    chip: 'Finishes',
    parts: ['floor_tile_sqm', 'wall_plaster_sqm', 'ceiling_sqm', 'door_count', 'window_count', 'paint_sqm'],
  },
  {
    key: 'services',
    code: 'ME',
    title: 'Section 03: MEP services, electrical & plumbing',
    chip: 'MEP services',
    parts: ['electrical_points', 'total_plumbing_fixtures'],
  },
] as const;

type Filter = 'all' | (typeof SECTIONS)[number]['key'] | 'other' | 'layer4';

interface BoqRow {
  code: string;
  part: string;
  line: TradeLine;
}

function groupLines(report: CostReport) {
  const known = new Set<string>(SECTIONS.flatMap((s) => s.parts));
  const sections = SECTIONS.map((s) => ({
    ...s,
    rows: s.parts
      .filter((p) => report.trade_breakdown[p])
      .map((p, i) => ({ code: `${s.code}-${101 + i}`, part: p, line: report.trade_breakdown[p] })),
  }));
  // Anything C02 starts pricing that this page does not know yet still shows.
  const other = Object.keys(report.trade_breakdown)
    .filter((p) => !known.has(p))
    .map((p, i) => ({ code: `OT-${101 + i}`, part: p, line: report.trade_breakdown[p] }));
  return { sections, other };
}

const sumRows = (rows: BoqRow[]) => rows.reduce((a, r) => a + Number(r.line.line_cost_lkr ?? 0), 0);

function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** The whole priced BOQ as CSV, built in the browser from the response. */
function downloadBoq(report: CostReport, projectName: string) {
  const { sections, other } = groupLines(report);
  const lines: string[][] = [
    ['Code', 'Section', 'Work item', 'Description', 'Quantity', 'Unit', 'Base rate (LKR)', 'Escalated rate (LKR)', 'Total (LKR)'],
  ];
  for (const s of [...sections, { title: 'Other items', rows: other }]) {
    for (const r of s.rows) {
      lines.push([
        r.code,
        s.title,
        workItemLabel(r.part),
        r.line.description ?? '',
        String(r.line.quantity ?? ''),
        r.line.unit ?? '',
        String(r.line.base_rate_lkr ?? ''),
        String(r.line.adjusted_rate_lkr ?? r.line.rate_lkr ?? ''),
        String(r.line.line_cost_lkr ?? ''),
      ]);
    }
  }
  lines.push(['', '', 'Direct cost', '', '', '', '', '', String(report.summary.direct_cost_lkr)]);
  report.contingency_breakdown.forEach((c, i) => {
    lines.push([`PR-${401 + i}`, 'Layer 4 contingency & mark-ups', titleCase(c.item), '', String(c.rate_pct), '%', '', '', String(c.amount_lkr)]);
  });
  lines.push(['', '', 'Total', '', '', '', '', '', String(report.summary.total_lkr)]);

  const blob = new Blob([lines.map((l) => l.map(csvCell).join(',')).join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `boq-${(projectName || 'plan').replace(/[^\w-]+/g, '-').toLowerCase()}-${report.estimate_id.slice(0, 8)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/** "Rs 19.75–26.46M": a range compact enough for a tile. */
const rangeText = (lo: number, hi: number) => `Rs ${(lo / 1e6).toFixed(2)}–${(hi / 1e6).toFixed(2)}M`;

/** A band given as zeros means C02 had no model to compute it with. */
const band = (lo?: number, hi?: number) => (lo && hi && hi > lo ? { lo, hi } : null);

type Props = { run: RunState; update: (p: Partial<RunState>) => void };

export function Step2Cost({ run, update }: Props) {
  const nav = useNavigate();
  const schema = run.step1?.buildingSchema;

  const [materials, setMaterials] = useState<Record<string, string>>(run.step2?.materials ?? {});
  const [report, setReport] = useState<CostReport | undefined>(run.step2?.estimate);
  const [filter, setFilter] = useState<Filter>('all');

  const catalog = useQuery({ queryKey: ['materials'], queryFn: fetchMaterials });

  const runEstimate = useMutation({
    mutationFn: (m: Record<string, string>) => estimate(schema!, m),
    onSuccess: (r, m) => {
      setReport(r);
      update({ step2: { estimate: r, materials: m }, step3: undefined, step4: undefined });
    },
  });

  // Estimate once on arrival, then re-estimate (debounced) whenever the user
  // changes a material so the numbers track the picker without a manual click.
  const firstRun = useRef(false);
  useEffect(() => {
    if (!schema) return;
    if (!firstRun.current) {
      firstRun.current = true;
      if (report) return; // already have one from a previous visit
    }
    const t = setTimeout(() => runEstimate.mutate(materials), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materials, schema]);

  const grouped = useMemo(() => (report ? groupLines(report) : null), [report]);

  if (!schema) {
    return (
      <div className="alert warn">
        No design yet. <Link to="/step/1">Start at step 1</Link>.
      </div>
    );
  }

  if (!report) {
    return runEstimate.isError ? (
      <ErrorBox error={runEstimate.error} onRetry={() => runEstimate.mutate(materials)} />
    ) : (
      <Loading what="Pricing the bill of quantities" />
    );
  }

  const s = report.summary;
  const rm = report.rate_metadata;
  const fd = report.feeds_downstream;
  const calibrated = s.interval_is_calibrated === true;
  const likely = band(s.lower_bound_lkr, s.upper_bound_lkr);
  const b90 = band(s.interval_90_lkr?.lower_lkr, s.interval_90_lkr?.upper_lkr);
  const budget = s.budget_lkr && s.budget_lkr > 0 ? s.budget_lkr : null;
  const likelyPct = Math.round(s.confidence_level * 100);
  const margin = s.total_lkr - s.direct_cost_lkr;
  const marginPct = s.direct_cost_lkr > 0 ? (margin / s.direct_cost_lkr) * 100 : 0;
  const riskPct = report.risk_factors_applied.reduce((a, f) => a + f.added_pct, 0);
  const coastal = report.risk_factors_applied.some((f) => f.factor === 'coastal_site');
  const lineCount = Object.keys(report.trade_breakdown).length;
  const modelDelta = s.total_lkr > 0 ? ((s.ml_point_estimate_lkr - s.total_lkr) / s.total_lkr) * 100 : 0;

  // The band's scale: 90% band (or the likely range) plus the budget marker, padded.
  const lo = Math.min(b90?.lo ?? likely?.lo ?? s.total_lkr, s.total_lkr);
  const hi = Math.max(b90?.hi ?? likely?.hi ?? s.total_lkr, budget ?? 0, s.total_lkr);
  const pad = (hi - lo) * 0.06 || s.total_lkr * 0.05;
  const at = (v: number) => `${((v - (lo - pad)) / (hi - lo + 2 * pad)) * 100}%`;
  const span = (a: number, b: number) => ({ left: at(a), width: `calc(${at(b)} - ${at(a)})` });

  const maxShap = Math.max(1, ...report.shap_top_drivers.map((d) => Math.abs(d.impact_lkr)));

  const sections = grouped?.sections ?? [];
  const other = grouped?.other ?? [];
  const show = (key: Filter) => filter === 'all' || filter === key;

  return (
    <div className="cs">
      <div className="cs-head">
        <div>
          <span className="chip ink">C02 // Cost estimation</span>
          <h1>{run.projectName ? `${run.projectName} — cost estimate` : 'Cost estimate'}</h1>
          <div className="meta">
            {num(fd.floor_area_sqm, 2)} m² floor area · {fd.floors} level{fd.floors === 1 ? '' : 's'} ·{' '}
            {num(schema.footprint_sqm, 2)} m² footprint · {titleCase(schema.finish_grade)} grade
            {rm.district ? ` · ${rm.district}` : ''}
          </div>
        </div>
        <div className="cs-head-side">
          <div className="btn-row">
            <span className="chip">
              Rate base: <b>ICTAD {rm.base_date} → {rm.target_date}</b>
            </span>
          </div>
          <div className="btn-row">
            <span className="chip">
              Price factor:{' '}
              <b className="terra">
                {num(rm.escalation_factor, 3)}× escalation{coastal ? ' & coastal adj.' : ''}
              </b>
            </span>
            {runEstimate.isPending && (
              <span className="cs-busy">
                <span className="spinner" aria-hidden /> Re-pricing…
              </span>
            )}
            <button className="sm" onClick={() => downloadBoq(report, run.projectName)}>
              Export BOQ (CSV)
            </button>
            <button className="primary sm" onClick={() => nav('/step/3')}>
              Handoff to C03 →
            </button>
          </div>
        </div>
      </div>

      {runEstimate.isError && (
        <ErrorBox error={runEstimate.error} onRetry={() => runEstimate.mutate(materials)} />
      )}

      <div className="cs-layers">
        <div className="cs-layer">
          <div className="between">
            <span className="eyebrow dim">Layer 01 // Quantities</span>
            <span className="eyebrow dim">L1-BOQ</span>
          </div>
          <h3>BOQ take-off engine</h3>
          <p>Structural, finishing and services quantities measured from your design.</p>
          <span className="foot">
            <span className="dot" /> {lineCount} BOQ items computed
          </span>
        </div>
        <div className="cs-layer">
          <div className="between">
            <span className="eyebrow dim">Layer 02 // Unit rates</span>
            <span className="eyebrow dim">L2-Rates</span>
          </div>
          <h3>ICTAD rate engine</h3>
          <p>
            Base rates from {rm.base_date}, escalated ×{num(rm.escalation_factor, 3)} to {rm.target_date}
            {rm.district ? ` for ${rm.district}` : ''}.
          </p>
          <span className="foot">
            <span className="dot" /> Escalated to target date
          </span>
        </div>
        <div className="cs-layer hot">
          <div className="between">
            <span className="eyebrow">Layer 03 // ML quantile</span>
            <span className="eyebrow">L3-XGBoost</span>
          </div>
          <h3>Conformal predictor</h3>
          <p>
            XGBoost quantile model with conformal offsets, so the cost bands hold their stated
            coverage.
          </p>
          <span className="foot">
            <span className={`dot ${calibrated ? 'terra' : 'ochre'}`} />
            {calibrated ? 'Intervals calibrated' : 'Uncalibrated intervals'}
          </span>
        </div>
        <div className="cs-layer">
          <div className="between">
            <span className="eyebrow dim">Layer 04 // Contingency</span>
            <span className="eyebrow dim">L4-Risk</span>
          </div>
          <h3>Site risk adjuster</h3>
          <p>
            {report.risk_factors_applied.length > 0
              ? report.risk_factors_applied
                  .map((f) => `${titleCase(f.factor)} +${num(f.added_pct)}%`)
                  .join(', ')
              : 'No site risk loadings applied'}
            , then site, supervision and mark-ups.
          </p>
          <span className="foot">
            <span className="dot ochre" /> +{num(marginPct)}% on direct cost
            {riskPct > 0 ? ` · risk +${num(riskPct)}%` : ''}
          </span>
        </div>
      </div>

      <div className="cs-main">
        <div>
          <section className="cs-panel">
            <div className="between" style={{ alignItems: 'flex-start' }}>
              <span className="eyebrow dim">Calibrated contract estimate</span>
              <div style={{ textAlign: 'right' }}>
                {calibrated ? (
                  <span className="chip nominal">Finite-sample calibrated</span>
                ) : (
                  <span className="chip review">Not calibrated</span>
                )}
                <div className="faint" style={{ marginTop: '0.35rem' }}>
                  Model point {lkr(s.ml_point_estimate_lkr, true)} ({modelDelta >= 0 ? '+' : '−'}
                  {num(Math.abs(modelDelta))}% vs BOQ)
                </div>
              </div>
            </div>
            <div className="cs-total">{lkr(s.total_lkr)}</div>

            {(likely || b90) && (
              <div className="cs-band">
                <div className="labels">
                  <span>{b90 ? `90% lower band: ${lkr(b90.lo, true)}` : `Lower: ${lkr(likely!.lo, true)}`}</span>
                  <span style={{ color: 'var(--text)' }}>Estimate: {lkr(s.total_lkr, true)}</span>
                  {budget && <span className="terra">Prudent 90% upper: {lkr(budget, true)}</span>}
                </div>
                <div
                  className="cs-track"
                  role="img"
                  aria-label={`Estimate ${lkr(s.total_lkr)}${likely ? `, ${likelyPct}% likely range ${lkr(likely.lo)} to ${lkr(likely.hi)}` : ''}${b90 ? `, 90% band ${lkr(b90.lo)} to ${lkr(b90.hi)}` : ''}`}
                >
                  {b90 && <div className="b90" style={span(b90.lo, b90.hi)} />}
                  {likely && (
                    <div className="b50" style={span(likely.lo, likely.hi)}>
                      <span>{likelyPct}% likely range</span>
                    </div>
                  )}
                  <div className="mark" style={{ left: at(s.total_lkr) }} title="Estimate" />
                  {budget && <div className="mark budget" style={{ left: at(budget) }} title="Budget figure" />}
                </div>
                <div className="scale">
                  <span>{b90 ? `α = 0.05: ${lkr(b90.lo, true)}` : ''}</span>
                  {likely && (
                    <span className="mid">
                      Likely: {lkr(likely.lo, true)} – {lkr(likely.hi, true)}
                    </span>
                  )}
                  <span className="terra">{b90 ? `α = 0.95: ${lkr(b90.hi, true)}` : ''}</span>
                </div>
              </div>
            )}

            <div className="cs-tiles">
              {likely && (
                <div className="cs-tile">
                  <span className="eyebrow dim">{likelyPct}% likely range</span>
                  <div className="v">{rangeText(likely.lo, likely.hi)}</div>
                  <p>Where half of comparable projects land. A sensible procurement target.</p>
                  <span className="delta">Δ {lkr(likely.hi - likely.lo, true)} width</span>
                </div>
              )}
              {budget && (
                <div className="cs-tile hot">
                  <span className="eyebrow">Prudent budget (one-sided 90%)</span>
                  <div className="v">{lkr(budget)}</div>
                  <p>90% of comparable projects come in at or below this figure.</p>
                  <span className="delta">
                    +{lkr(budget - s.total_lkr, true)} above the estimate
                  </span>
                </div>
              )}
              {b90 && (
                <div className="cs-tile">
                  <span className="eyebrow dim">Full 90% risk band</span>
                  <div className="v">{rangeText(b90.lo, b90.hi)}</div>
                  <p>Two-sided band for analysis, roughly three times the likely range.</p>
                  <span className="delta">
                    {Math.round(((b90.hi - b90.lo) / s.total_lkr) * 100)}% of the estimate wide
                  </span>
                </div>
              )}
            </div>
          </section>

          <div className={`cs-notice${calibrated ? '' : ' warn'}`}>
            <svg viewBox="0 0 20 20" aria-hidden>
              <circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
              {calibrated ? (
                <path d="m6.3 10.2 2.5 2.5 4.9-5.1" fill="none" stroke="currentColor" strokeWidth="1.6" />
              ) : (
                <path d="M10 5.5v5.5M10 13.4v1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
              )}
            </svg>
            <div>
              <b>{calibrated ? 'Conformal validity verified' : 'Calibration unavailable'}</b>
              <p>
                {calibrated
                  ? 'The bands carry conformal offsets fitted on held-out projects, so their coverage holds in finite samples without assuming how costs are distributed.'
                  : 'C02 could not load its conformal offsets, so these bands are raw quantile estimates. Treat them as indicative only.'}
              </p>
            </div>
          </div>
        </div>

        <section className="cs-panel cs-drivers">
          <div className="between">
            <span className="eyebrow">Explainable ML // Layer 3 SHAP</span>
            <span className="eyebrow dim">Top {report.shap_top_drivers.length}</span>
          </div>
          <h2>Cost driver attribution</h2>
          <p>How much each feature moved the model's estimate for this design, in rupees.</p>
          {report.shap_top_drivers.length === 0 ? (
            <p className="faint">No drivers returned.</p>
          ) : (
            report.shap_top_drivers.map((d, i) => {
              const up = d.direction === 'increases';
              return (
                <div className="cs-driver" key={i}>
                  <div className="between">
                    <span>
                      {i + 1}. {titleCase(d.feature)}
                    </span>
                    <span className={`amt ${up ? 'up' : 'down'}`}>
                      {up ? '+' : '−'}
                      {lkr(Math.abs(d.impact_lkr))}
                    </span>
                  </div>
                  <div className="track">
                    <span
                      className={up ? '' : 'down'}
                      style={{ width: `${(Math.abs(d.impact_lkr) / maxShap) * 100}%` }}
                    />
                  </div>
                  <small>{up ? 'Pushes the estimate up' : 'Pulls the estimate down'}</small>
                </div>
              );
            })
          )}
          <div className="cs-meta">
            <span>
              Model: <b>{modelName(report.model_metadata.model)} quantile</b>
            </span>
            <span>
              Price factor: <b>×{num(Number(report.model_metadata.price_factor ?? rm.escalation_factor), 3)}</b>
            </span>
            <span>
              Per m²: <b>{lkr(s.cost_per_sqm_lkr)}</b>
            </span>
            <span>
              Labour: <b>{fd.total_labour_days.toLocaleString('en-LK')} days</b>
            </span>
          </div>
        </section>
      </div>

      <Card
        title="Material specification"
        subtitle={
          catalog.data
            ? `${Object.keys(catalog.data).length} work items · ${Object.keys(materials).length} customised · unset items use the ${schema.finish_grade} grade default`
            : undefined
        }
        actions={
          Object.keys(materials).length > 0 ? (
            <button className="ghost sm" onClick={() => setMaterials({})}>
              Reset to defaults
            </button>
          ) : undefined
        }
      >
        {catalog.isPending && <Loading what="Loading material catalogue" />}
        {catalog.isError && <ErrorBox error={catalog.error} onRetry={() => catalog.refetch()} />}
        {catalog.data && (
          <div className="cs-materials">
            {Object.entries(catalog.data).map(([part, variants]) => {
              const chosen = materials[part] ?? '';
              const active = variants.find((v) => v.material === chosen);
              const qty = partQuantity(report, part);
              return (
                <label className="field" key={part}>
                  <span className="row">
                    {workItemLabel(part)}
                    {qty && <span className="faint">{qty}</span>}
                    {chosen && <Badge tone="ok">custom</Badge>}
                  </span>
                  <select
                    value={chosen}
                    onChange={(e) => {
                      const next = { ...materials };
                      if (e.target.value) next[part] = e.target.value;
                      else delete next[part];
                      setMaterials(next);
                    }}
                  >
                    <option value="">Grade default</option>
                    {variants.map((v) => (
                      <option key={v.material} value={v.material}>
                        {v.description} — {lkr(v.rate_lkr)}/{v.unit}
                      </option>
                    ))}
                  </select>
                  {active && (
                    <span className="faint">
                      {lkr(active.rate_lkr)}/{active.unit} · {active.rate_source}
                    </span>
                  )}
                </label>
              );
            })}
          </div>
        )}
      </Card>

      <section className="cs-boq">
        <header>
          <div>
            <span className="eyebrow dim">Bill of quantities (BOQ) schedule</span>
            <h2>Layer 1 &amp; Layer 2 itemised rate analysis</h2>
          </div>
          <div className="cs-filters" role="group" aria-label="Filter trade">
            <span className="eyebrow dim">Filter trade:</span>
            <button aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>
              All trades ({lineCount})
            </button>
            {sections.map((sec, i) =>
              sec.rows.length > 0 ? (
                <button key={sec.key} aria-pressed={filter === sec.key} onClick={() => setFilter(sec.key)}>
                  {sec.chip} (0{i + 1})
                </button>
              ) : null,
            )}
            {other.length > 0 && (
              <button aria-pressed={filter === 'other'} onClick={() => setFilter('other')}>
                Other ({other.length})
              </button>
            )}
            <button aria-pressed={filter === 'layer4'} onClick={() => setFilter('layer4')}>
              Contingency (04)
            </button>
          </div>
        </header>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Trade item description</th>
                <th className="num">Quantity</th>
                <th>Unit</th>
                <th className="num">ICTAD base (LKR)</th>
                <th className="num">Escalated rate ({num(rm.escalation_factor, 3)}×)</th>
                <th className="num">Total (LKR)</th>
              </tr>
            </thead>
            <tbody>
              {[...sections, ...(other.length ? [{ key: 'other' as const, title: 'Other priced items', rows: other }] : [])].map(
                (sec) =>
                  show(sec.key) &&
                  sec.rows.length > 0 && (
                    <BoqSection key={sec.key} title={sec.title} rows={sec.rows} />
                  ),
              )}

              {show('layer4') && (
                <>
                  <tr className="section">
                    <td colSpan={7}>Section 04: Preliminaries, contingency &amp; mark-ups (Layer 4)</td>
                  </tr>
                  {report.contingency_breakdown.map((c, i) => (
                    <tr key={c.item}>
                      <td className="code">PR-{401 + i}</td>
                      <td>{titleCase(c.item)}</td>
                      <td className="num">{num(c.rate_pct)}</td>
                      <td>%</td>
                      <td className="num">—</td>
                      <td className="num">—</td>
                      <td className="num total">{amount(c.amount_lkr)}</td>
                    </tr>
                  ))}
                </>
              )}

              {filter === 'all' && (
                <>
                  <tr className="sum">
                    <td colSpan={6} className="lbl">
                      Direct work sum (before Layer 4)
                    </td>
                    <td className="num">{lkr(s.direct_cost_lkr)}</td>
                  </tr>
                  <tr className="sum terra">
                    <td colSpan={6} className="lbl">
                      Layer 4 risk margin &amp; mark-ups (+{num(marginPct, 2)}%)
                    </td>
                    <td className="num">{lkr(margin)}</td>
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>

        <div className="cs-final">
          <span>Final calibrated contract total{run.projectName ? ` (${run.projectName})` : ''}:</span>
          <strong>{lkr(s.total_lkr)}</strong>
        </div>
        <footer>
          <span>
            Showing {filter === 'all' ? `all ${lineCount}` : 'filtered'} priced items measured from your
            design
          </span>
          <button onClick={() => downloadBoq(report, run.projectName)}>Download complete BOQ (CSV)</button>
        </footer>
      </section>

      <div className="cs-status">
        <div className="chips">
          <span className="chip">
            <span className={`dot ${calibrated ? '' : 'ochre'}`} /> Interval calibrated:{' '}
            <b>{calibrated ? 'Yes' : 'No'}</b>
          </span>
          <span className="chip">
            Rate base: <b>ICTAD {rm.base_date}</b>
          </span>
          {rm.district && (
            <span className="chip">
              Location: <b>{[rm.district, rm.province].filter(Boolean).join(', ')}</b>
            </span>
          )}
          <span className="chip">
            Coverage target: <b className="terra">1 − α = 0.90</b>
          </span>
        </div>
        <div className="btn-row">
          <button className="ghost" onClick={() => nav('/step/1')}>
            ← Design
          </button>
          <button disabled={runEstimate.isPending} onClick={() => runEstimate.mutate(materials)}>
            Recalculate estimate
          </button>
          <button className="primary" onClick={() => nav('/step/3')}>
            Proceed to C03 timeline &amp; CPM →
          </button>
        </div>
      </div>
    </div>
  );
}

const modelName = (m: unknown) => {
  const s = String(m ?? 'xgboost');
  return s.toLowerCase() === 'xgboost' ? 'XGBoost' : titleCase(s);
};

const amount = (n: number | null | undefined) =>
  n === null || n === undefined || Number.isNaN(n)
    ? '—'
    : n.toLocaleString('en-LK', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function BoqSection({ title, rows }: { title: string; rows: BoqRow[] }) {
  return (
    <>
      <tr className="section">
        <td colSpan={6}>{title}</td>
        <td className="num">{amount(sumRows(rows))}</td>
      </tr>
      {rows.map(({ code, part, line }) => (
        <tr key={part}>
          <td className="code">{code}</td>
          <td>
            {workItemLabel(part)}
            {line.description && <div className="faint">{line.description}</div>}
          </td>
          <td className="num">{amount(line.quantity)}</td>
          <td>{line.unit === 'nr' ? 'Nr' : (line.unit ?? '')}</td>
          <td className="num">{amount(line.base_rate_lkr)}</td>
          <td className="num esc">{amount(line.adjusted_rate_lkr ?? line.rate_lkr)}</td>
          <td className="num total">{amount(line.line_cost_lkr)}</td>
        </tr>
      ))}
    </>
  );
}
