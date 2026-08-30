import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { estimate, fetchMaterials } from '../api/services';
import { Badge, Card, ErrorBox, Loading, Stat, lkr, num, qtyText, titleCase, workItemLabel } from '../components/ui';
import type { CostReport, RunState } from '../types';
/** How much of this item C02 measured off the building schema, e.g. "9 nr" or
 *  "156 m²". Read from trade_breakdown, which carries quantity and unit for
 *  every priced line - so the picker shows what is actually being bought. */
function partQuantity(report: CostReport | undefined, part: string): string | null {
  const line = report?.trade_breakdown?.[part];
  if (!line || typeof line.quantity !== 'number') return null;
  return qtyText(line.quantity, line.unit);
}

type Props = { run: RunState; update: (p: Partial<RunState>) => void };

export function Step2Cost({ run, update }: Props) {
  const nav = useNavigate();
  const schema = run.step1?.buildingSchema;

  const [materials, setMaterials] = useState<Record<string, string>>(run.step2?.materials ?? {});
  const [report, setReport] = useState<CostReport | undefined>(run.step2?.estimate);

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

  const tradeData = useMemo(() => {
    if (!report) return [];
    return Object.entries(report.trade_breakdown)
      .map(([k, v]) => ({ name: workItemLabel(k), value: Number(v?.line_cost_lkr ?? 0) }))
      .filter((d) => d.value > 0)
      .sort((a, b) => b.value - a.value)
      .slice(0, 12);
  }, [report]);

  if (!schema) {
    return (
      <div className="alert warn">
        No design yet. <Link to="/step/1">Start at step 1</Link>.
      </div>
    );
  }

  const s = report?.summary;

  return (
    <div className="stack">
      <div className="between">
        <div>
          <h1>Materials &amp; Cost</h1>
          <p className="muted">
            Pick materials per work item. Unset items use the {schema.finish_grade} grade default.
          </p>
        </div>
        {runEstimate.isPending && (
          <span className="row muted">
            <span className="spinner" aria-hidden /> Re-pricing…
          </span>
        )}
      </div>

      {runEstimate.isError && (
        <ErrorBox error={runEstimate.error} onRetry={() => runEstimate.mutate(materials)} />
      )}

      {s && (
        <div className="grid cols-4">
          <Stat
            label="Total cost"
            value={lkr(s.total_lkr)}
            hint={`${lkr(s.lower_bound_lkr, true)} – ${lkr(s.upper_bound_lkr, true)} at ${Math.round(
              s.confidence_level * 100,
            )}%`}
          />
          <Stat label="Per m²" value={lkr(s.cost_per_sqm_lkr)} />
          <Stat label="Direct cost" value={lkr(s.direct_cost_lkr, true)} hint="before contingency" />
          <Stat label="ML estimate" value={lkr(s.ml_point_estimate_lkr, true)} hint="model point value" />
        </div>
      )}

      <Card
        title="Materials"
        subtitle={
          catalog.data
            ? `${Object.keys(catalog.data).length} work items · ${
                Object.keys(materials).length
              } customised`
            : undefined
        }
        actions={
          Object.keys(materials).length > 0 ? (
            <button className="ghost" onClick={() => setMaterials({})}>
              Reset to defaults
            </button>
          ) : undefined
        }
      >
        {/* What C02 measured off the design. These are the quantities every
            rate below is multiplied by, so showing them makes the pricing
            legible instead of a bare per-unit menu. */}
        {report && (
          <div className="grid cols-4" style={{ marginBottom: '0.9rem' }}>
            <Stat
              label="Floor area"
              value={`${num(report.feeds_downstream.floor_area_sqm, 0)} m²`}
              hint={`${report.feeds_downstream.floors} floor(s)`}
            />
            <Stat label="Doors" value={partQuantity(report, 'door_count') ?? '—'} />
            <Stat label="Windows" value={partQuantity(report, 'window_count') ?? '—'} />
            <Stat label="Roof area" value={partQuantity(report, 'roof_area_sqm') ?? '—'} />
          </div>
        )}

        {catalog.isPending && <Loading what="Loading material catalogue" />}
        {catalog.isError && <ErrorBox error={catalog.error} onRetry={() => catalog.refetch()} />}
        {catalog.data && (
          <div className="grid cols-2">
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

      {report && (
        <>
          <Card title="Cost by trade" subtitle="Top items by line cost">
            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer>
                <BarChart data={tradeData} layout="vertical" margin={{ left: 30, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis
                    type="number"
                    tickFormatter={(v) => lkr(Number(v), true)}
                    stroke="var(--text-faint)"
                    fontSize={11}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={150}
                    stroke="var(--text-faint)"
                    fontSize={11}
                  />
                  <Tooltip
                    cursor={{ fill: 'var(--border)', opacity: 0.25 }}
                    formatter={(v) => [lkr(Number(v)), 'Line cost']}
                    contentStyle={{
                      background: 'var(--surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      color: 'var(--text)',
                    }}
                    /* contentStyle only colours the container - Recharts writes
                       its own colour onto the label and each value row, which
                       defaulted to near-black and vanished on the dark card. */
                    labelStyle={{ color: 'var(--text)', fontWeight: 600 }}
                    itemStyle={{ color: 'var(--text)' }}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {tradeData.map((_, i) => (
                      <Cell key={i} fill="var(--accent)" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="grid cols-2">
            <Card title="Top cost drivers" subtitle="SHAP attribution from the ML model">
              {report.shap_top_drivers.length === 0 ? (
                <p className="faint">No drivers returned.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Feature</th>
                        <th className="num">Impact</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.shap_top_drivers.map((d, i) => (
                        <tr key={i}>
                          <td>
                            {d.direction === 'increases' ? '▲' : '▼'} {titleCase(d.feature)}
                          </td>
                          <td
                            className="num"
                            style={{
                              color: d.direction === 'increases' ? 'var(--danger)' : 'var(--ok)',
                            }}
                          >
                            {d.direction === 'increases' ? '+' : '−'}
                            {lkr(Math.abs(d.impact_lkr), true)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Contingency build-up">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th className="num">Rate</th>
                      <th className="num">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.contingency_breakdown.map((c, i) => (
                      <tr key={i}>
                        <td>{titleCase(c.item)}</td>
                        <td className="num">{num(c.rate_pct)}%</td>
                        <td className="num">{lkr(c.amount_lkr, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <hr className="divider" />
              <div className="faint">
                Escalation ×{num(report.rate_metadata.escalation_factor, 3)} ·{' '}
                {report.rate_metadata.base_date} → {report.rate_metadata.target_date} ·{' '}
                {report.rate_metadata.district}, {report.rate_metadata.province}
              </div>
            </Card>
          </div>
        </>
      )}

      <div className="footer-nav">
        <button onClick={() => nav('/step/1')}>← Design</button>
        <button className="primary" onClick={() => nav('/step/3')} disabled={!report}>
          Move to Timeline →
        </button>
      </div>
    </div>
  );
}
