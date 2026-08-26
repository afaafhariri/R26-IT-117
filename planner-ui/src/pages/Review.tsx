import { Link } from 'react-router-dom';
import { Badge, Stat, dateStr, lkr, num, pct, titleCase, toneFor } from '../components/ui';
import type { RunState } from '../types';

/* Reads only from the persisted run — no network calls. C02 and C03 keep no
 * state of their own, so this page is the only place the full picture exists. */

function Section({
  n,
  title,
  done,
  children,
  emptyHint,
}: {
  n: number;
  title: string;
  done: boolean;
  children: React.ReactNode;
  emptyHint: string;
}) {
  return (
    <details className="section card" open={done}>
      <summary>
        {n}. {title}
        {done ? <Badge tone="ok">complete</Badge> : <Badge tone="neutral">not done</Badge>}
      </summary>
      {done ? children : <p className="faint">{emptyHint}</p>}
    </details>
  );
}

export function Review({ run }: { run: RunState }) {
  const schema = run.step1?.buildingSchema;
  const est = run.step2?.estimate;
  const tl = run.step3?.timeline;
  const entries = run.step4?.entries ?? [];
  const latest = entries[entries.length - 1];

  return (
    <div className="stack">
      <div className="between">
        <div>
          <h1>{run.projectName}</h1>
          <p className="muted">
            {schema?.district ?? '—'}
            {schema?.province ? `, ${schema.province}` : ''} · run{' '}
            <span className="mono">{run.runId.slice(0, 8)}</span> · updated{' '}
            {dateStr(run.updatedAt)}
          </p>
        </div>
        <button onClick={() => window.print()}>Print / Save PDF</button>
      </div>

      <div className="grid cols-4">
        <Stat
          label="Total cost"
          value={est ? lkr(est.summary.total_lkr, true) : '—'}
          hint={
            est
              ? `${lkr(est.summary.lower_bound_lkr, true)} – ${lkr(est.summary.upper_bound_lkr, true)}`
              : 'not estimated'
          }
        />
        <Stat
          label="Duration"
          value={tl ? `${num(tl.total_project_duration_weeks)} wk` : '—'}
          hint={tl?.total_project_duration_days ? `${tl.total_project_duration_days} days` : undefined}
        />
        <Stat
          label="Floor area"
          value={schema ? `${(schema.footprint_sqm * schema.floors).toFixed(0)} m²` : '—'}
          hint={schema ? `${schema.floors} floor(s)` : undefined}
        />
        <Stat
          label="Delay risk"
          value={
            latest?.prediction ? (
              <Badge tone={toneFor(latest.prediction.prediction.delay_risk)}>
                {latest.prediction.prediction.delay_risk}
              </Badge>
            ) : (
              '—'
            )
          }
          hint={
            latest?.prediction
              ? `${latest.prediction.prediction.estimated_delay_days} days`
              : 'no progress recorded'
          }
        />
      </div>

      <Section
        n={1}
        title="Design"
        done={!!schema}
        emptyHint="No design captured yet."
      >
        {schema && (
          <div className="grid cols-4">
            <Stat label="Footprint" value={`${schema.footprint_sqm} m²`} />
            <Stat label="Perimeter" value={`${schema.perimeter} m`} />
            <Stat label="Floors" value={schema.floors} />
            <Stat label="Plot area" value={`${schema.plot_area} m²`} />
            <Stat label="Finish grade" value={titleCase(schema.finish_grade)} />
            <Stat label="Roof" value={titleCase(schema.roof_type)} />
            <Stat label="Terrain" value={titleCase(schema.terrain)} />
            <Stat label="Rooms" value={schema.room_count} hint={`${schema.bathroom_count} bath`} />
          </div>
        )}
      </Section>

      <Section
        n={2}
        title="Cost"
        done={!!est}
        emptyHint="No estimate produced yet."
      >
        {est && (
          <div className="stack">
            <div className="grid cols-3">
              <Stat label="Total" value={lkr(est.summary.total_lkr)} />
              <Stat label="Per m²" value={lkr(est.summary.cost_per_sqm_lkr)} />
              <Stat label="Direct cost" value={lkr(est.summary.direct_cost_lkr, true)} />
            </div>
            <div>
              <h3>Top cost drivers</h3>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {est.shap_top_drivers.map((d, i) => (
                      <tr key={i}>
                        <td>{titleCase(d.feature)}</td>
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
            </div>
            {Object.keys(run.step2?.materials ?? {}).length > 0 && (
              <div>
                <h3>Custom materials</h3>
                <div className="table-wrap">
                  <table>
                    <tbody>
                      {Object.entries(run.step2!.materials).map(([part, mat]) => (
                        <tr key={part}>
                          <td>{titleCase(part)}</td>
                          <td className="faint">{titleCase(mat)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            <div className="faint">
              Estimate <span className="mono">{est.estimate_id.slice(0, 8)}</span> ·{' '}
              {dateStr(est.generated_at)}
            </div>
          </div>
        )}
      </Section>

      <Section
        n={3}
        title="Schedule"
        done={!!tl}
        emptyHint="No timeline predicted yet."
      >
        {tl && (
          <div className="stack">
            <div className="grid cols-3">
              <Stat label="Total" value={`${num(tl.total_project_duration_weeks)} weeks`} />
              <Stat label="Confidence" value={pct(tl.confidence_score)} />
              <Stat label="Milestones" value={tl.milestones.length} />
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Start</th>
                    <th>End</th>
                    <th className="num">Weeks</th>
                  </tr>
                </thead>
                <tbody>
                  {tl.gantt_chart_data.map((t) => (
                    <tr key={t.id}>
                      <td>{t.task}</td>
                      <td className="faint">{dateStr(t.start_date)}</td>
                      <td className="faint">{dateStr(t.end_date)}</td>
                      <td className="num">{num(t.duration_weeks)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row">
              <span className="faint">Critical path:</span>
              {tl.critical_path.map((c) => (
                <Badge key={c} tone="danger">
                  {titleCase(c)}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Section>

      <Section
        n={4}
        title="Performance"
        done={!!run.step4?.c04ProjectId}
        emptyHint="Baseline not loaded into monitoring yet."
      >
        <div className="stack">
          <div className="faint">
            Monitoring project <span className="mono">#{run.step4?.c04ProjectId}</span>
          </div>
          {entries.length === 0 ? (
            <p className="faint">
              Baseline loaded, but no site progress recorded — so the delay model has not run.{' '}
              <Link to="/step/4">Record progress</Link>.
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Phase</th>
                    <th className="num">Actual</th>
                    <th className="num">SPI</th>
                    <th>Risk</th>
                    <th className="num">Delay</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e, i) => (
                    <tr key={i}>
                      <td>{e.phaseLabel}</td>
                      <td className="num">{num(e.actualPercent)}%</td>
                      <td className="num">{num(e.spi.spi_value, 2)}</td>
                      <td>
                        {e.prediction ? (
                          <Badge tone={toneFor(e.prediction.prediction.delay_risk)}>
                            {e.prediction.prediction.delay_risk}
                          </Badge>
                        ) : (
                          <Badge tone={toneFor(e.spi.alert_level)}>{e.spi.alert_level}</Badge>
                        )}
                      </td>
                      <td className="num">
                        {e.prediction ? `${e.prediction.prediction.estimated_delay_days} d` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {latest?.prediction?.recommendation?.explanation && (
            <div>
              <h3>Latest recommendation</h3>
              <p className="muted">{latest.prediction.recommendation.explanation}</p>
            </div>
          )}
        </div>
      </Section>

      <div className="footer-nav">
        <button onClick={() => window.history.back()}>← Back</button>
        <Link to="/step/1">
          <button className="ghost">Edit design</button>
        </Link>
      </div>
    </div>
  );
}
