import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDashboard, predictDelay, seedSchedule, submitSpi } from '../api/services';
import { Badge, Card, ErrorBox, Loading, Stat, dateStr, num, pct, titleCase, toneFor } from '../components/ui';
import {
  DELAY_CATEGORIES,
  LABOUR_AVAILABILITY,
  MATERIAL_SUPPLY,
  WEATHER_SEVERITY,
} from '../types';
import type { PredictResponse, RunState, SpiResponse } from '../types';

type Props = { run: RunState; update: (p: Partial<RunState>) => void };

export function Step4Performance({ run, update }: Props) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const payload = run.step3?.schedulePayload;
  const projectId = run.step4?.c04ProjectId;

  const seed = useMutation({
    mutationFn: () => seedSchedule(payload!),
    onSuccess: (r) =>
      update({ step4: { c04ProjectId: r.project_id, entries: run.step4?.entries ?? [] } }),
  });

  const dashboard = useQuery({
    queryKey: ['dashboard', projectId],
    queryFn: () => fetchDashboard(projectId!),
    enabled: !!projectId,
  });

  /* ── progress entry ── */
  const [phaseId, setPhaseId] = useState<number | ''>('');
  const [percent, setPercent] = useState(25);
  const [spi, setSpi] = useState<SpiResponse | null>(null);
  const [category, setCategory] = useState<string>(DELAY_CATEGORIES[0]);
  const [labour, setLabour] = useState<string>('Medium');
  const [supply, setSupply] = useState<string>('Yes');
  const [weather, setWeather] = useState<string>('');
  const [prediction, setPrediction] = useState<PredictResponse | null>(null);

  const spiMutation = useMutation({
    mutationFn: () => submitSpi(Number(phaseId), percent, 'planner-ui'),
    onSuccess: (r) => {
      setSpi(r);
      setPrediction(null);
      // Record it straight away. A NORMAL SPI never reaches the predict step
      // (C04 rejects it), so waiting for a prediction would lose the entry.
      const phase = dashboard.data?.phases.find((p) => p.phase_id === r.phase_id);
      update({
        step4: {
          c04ProjectId: projectId!,
          entries: [
            ...(run.step4?.entries ?? []),
            {
              phaseId: r.phase_id,
              phaseLabel: phase
                ? `${phase.phase_group} · ${phase.sub_phase}`
                : `Phase ${r.phase_id}`,
              actualPercent: r.actual_percent,
              spi: r,
              at: new Date().toISOString(),
            },
          ],
        },
      });
      qc.invalidateQueries({ queryKey: ['dashboard', projectId] });
    },
  });

  const predictMutation = useMutation({
    mutationFn: () =>
      predictDelay({
        spiId: spi!.spi_id,
        phaseId: spi!.phase_id,
        delayCategory: category,
        labourAvailability: labour,
        materialSupply: supply,
        weatherSeverity: weather || undefined,
      }),
    onSuccess: (r) => {
      setPrediction(r);
      // Attach the prediction to the entry the SPI step already created.
      update({
        step4: {
          c04ProjectId: projectId!,
          entries: (run.step4?.entries ?? []).map((e) =>
            e.spi.spi_id === r.spi_id ? { ...e, prediction: r } : e,
          ),
        },
      });
      qc.invalidateQueries({ queryKey: ['dashboard', projectId] });
    },
  });

  if (!payload) {
    return (
      <div className="alert warn">
        No schedule yet. <Link to="/step/3">Go back to step 3</Link>.
      </div>
    );
  }

  /* ── not seeded yet ── */
  if (!projectId) {
    return (
      <div className="stack">
        <h1>Performance</h1>
        <p className="muted">
          Load the planned schedule into monitoring, then record site progress to get a schedule
          performance index and a delay prediction.
        </p>
        {seed.isError && <ErrorBox error={seed.error} onRetry={() => seed.mutate()} />}
        <Card title="Baseline" subtitle={`${payload.phases.length} phases ready to load`}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Phase group</th>
                  <th>Sub-phase</th>
                  <th>Start</th>
                  <th>End</th>
                  <th className="num">Days</th>
                </tr>
              </thead>
              <tbody>
                {payload.phases.map((p) => (
                  <tr key={p.sequence}>
                    <td className="faint">{p.sequence}</td>
                    <td>{p.phase_group}</td>
                    <td className="faint">{p.sub_phase}</td>
                    <td>{dateStr(p.planned_start)}</td>
                    <td>{dateStr(p.planned_end)}</td>
                    <td className="num">{p.planned_duration_days}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <hr className="divider" />
          <button className="primary" onClick={() => seed.mutate()} disabled={seed.isPending}>
            {seed.isPending ? 'Loading…' : 'Load baseline into monitoring'}
          </button>
          <div className="faint" style={{ marginTop: '0.5rem' }}>
            Creates the project in Performance. Only do this once — repeating it creates a duplicate.
          </div>
        </Card>
        <div className="footer-nav">
          <button onClick={() => nav('/step/3')}>← Timeline</button>
          <span />
        </div>
      </div>
    );
  }

  /* ── seeded ── */
  const d = dashboard.data;
  const started = d?.phases.filter((p) => (p.actual_percent ?? 0) > 0).length ?? 0;

  return (
    <div className="stack">
      <div className="between">
        <div>
          <h1>Performance</h1>
          <p className="muted">
            Monitoring project <span className="mono">#{projectId}</span> · record progress to run
            the delay model.
          </p>
        </div>
        <button onClick={() => dashboard.refetch()} disabled={dashboard.isFetching}>
          {dashboard.isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {dashboard.isPending && <Loading what="Loading dashboard" />}
      {dashboard.isError && <ErrorBox error={dashboard.error} onRetry={() => dashboard.refetch()} />}

      {d && (
        <>
          <div className="grid cols-4">
            <Stat label="Phases" value={d.project_summary.total_phases} hint={`${started} started`} />
            <Stat
              label="Duration"
              value={`${d.project_summary.total_duration_days ?? '—'} d`}
              hint={`${dateStr(d.project_summary.overall_start)} → ${dateStr(
                d.project_summary.overall_end,
              )}`}
            />
            <Stat label="Alerts" value={d.active_alerts.length} />
            <Stat label="Location" value={`${d.project.district}`} hint={d.project.province} />
          </div>

          {started === 0 && (
            <div className="alert info">
              <span className="title">Nothing recorded yet.</span> Every phase reads “Not Started”
              until you enter progress below — that is also what feeds the delay-prediction model.
            </div>
          )}

          <Card title="Record site progress" subtitle="Step 1 of 2 — schedule performance index">
            <div className="grid cols-3">
              <label className="field">
                Phase
                <select
                  value={phaseId}
                  onChange={(e) => {
                    setPhaseId(e.target.value ? Number(e.target.value) : '');
                    setSpi(null);
                    setPrediction(null);
                  }}
                >
                  <option value="">Select a phase…</option>
                  {d.phases.map((p) => (
                    <option key={p.phase_id} value={p.phase_id}>
                      {p.sequence}. {p.phase_group} — {p.sub_phase}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Actual complete: {percent}%
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={percent}
                  onChange={(e) => setPercent(Number(e.target.value))}
                />
              </label>
              <label className="field">
                &nbsp;
                <button
                  className="primary"
                  onClick={() => spiMutation.mutate()}
                  disabled={phaseId === '' || spiMutation.isPending}
                >
                  {spiMutation.isPending ? 'Calculating…' : 'Calculate SPI'}
                </button>
              </label>
            </div>

            {spiMutation.isError && <ErrorBox error={spiMutation.error} />}

            {spi && (
              <>
                <hr className="divider" />
                <div className="grid cols-4">
                  <Stat label="SPI" value={num(spi.spi_value, 2)} />
                  <Stat label="Planned" value={`${num(spi.planned_percent)}%`} />
                  <Stat label="Actual" value={`${num(spi.actual_percent)}%`} />
                  <Stat
                    label="Alert level"
                    value={<Badge tone={toneFor(spi.alert_level)}>{spi.alert_level}</Badge>}
                  />
                </div>
                {spi.requires_prediction_step ? (
                  <div className="alert warn" style={{ marginTop: '1rem' }}>
                    Behind schedule — run the delay prediction below.
                  </div>
                ) : (
                  <div className="alert info" style={{ marginTop: '1rem' }}>
                    <span className="title">On track — no delay prediction needed.</span>{' '}
                    Performance only runs the delay model when SPI is WARNING or CRITICAL. A
                    phase whose planned start is still in the future always scores 1.00, so to
                    exercise the model pick a phase already underway (or set an earlier planned
                    start in step 3) and enter a percentage below its expected progress.
                  </div>
                )}
              </>
            )}
          </Card>

          {spi?.requires_prediction_step && (
            <Card title="Predict delay" subtitle="Step 2 of 2 — site conditions for the ML model">
              <div className="grid cols-2">
                <label className="field">
                  Delay category
                  <select value={category} onChange={(e) => setCategory(e.target.value)}>
                    {DELAY_CATEGORIES.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Labour availability
                  <select value={labour} onChange={(e) => setLabour(e.target.value)}>
                    {LABOUR_AVAILABILITY.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Material supply adequate
                  <select value={supply} onChange={(e) => setSupply(e.target.value)}>
                    {MATERIAL_SUPPLY.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Weather override
                  <span className="faint">optional — fetched automatically if blank</span>
                  <select value={weather} onChange={(e) => setWeather(e.target.value)}>
                    <option value="">Fetch automatically</option>
                    {WEATHER_SEVERITY.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
              </div>
              <hr className="divider" />
              <button
                className="primary"
                onClick={() => predictMutation.mutate()}
                disabled={predictMutation.isPending}
              >
                {predictMutation.isPending ? 'Predicting…' : 'Predict delay'}
              </button>

              {predictMutation.isError && <ErrorBox error={predictMutation.error} />}

              {prediction && (
                <>
                  <hr className="divider" />
                  <div className="grid cols-3">
                    <Stat
                      label="Delay risk"
                      value={
                        <Badge tone={toneFor(prediction.prediction.delay_risk)}>
                          {prediction.prediction.delay_risk}
                        </Badge>
                      }
                    />
                    <Stat
                      label="Estimated delay"
                      value={`${prediction.prediction.estimated_delay_days} d`}
                    />
                    <Stat label="Confidence" value={pct(prediction.prediction.confidence)} />
                  </div>
                  {prediction.recommendation?.explanation && (
                    <>
                      <hr className="divider" />
                      <h3>Recommendation</h3>
                      <p className="muted">{prediction.recommendation.explanation}</p>
                    </>
                  )}
                  {prediction.weather_used?.weather_severity && (
                    <div className="faint">
                      Weather: {prediction.weather_used.weather_severity} (
                      {prediction.weather_used.source})
                      {prediction.weather_used.temperature_c != null &&
                        ` · ${prediction.weather_used.temperature_c}°C`}
                    </div>
                  )}
                </>
              )}
            </Card>
          )}

          <Card title="Phases">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Phase</th>
                    <th>Planned</th>
                    <th className="num">Expected</th>
                    <th className="num">Actual</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {d.phases.map((p) => (
                    <tr key={p.phase_id}>
                      <td className="faint">{p.sequence}</td>
                      <td>
                        {p.phase_group}
                        <div className="faint">{p.sub_phase}</div>
                      </td>
                      <td className="faint">
                        {dateStr(p.planned_start)} → {dateStr(p.planned_end)}
                      </td>
                      <td className="num">{num(p.expected_progress_percent)}%</td>
                      <td className="num">
                        {p.actual_percent == null ? '—' : `${num(p.actual_percent)}%`}
                      </td>
                      <td>
                        <Badge tone={toneFor(p.status)}>{titleCase(p.status)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {d.active_alerts.length > 0 && (
            <Card title="Active alerts">
              {d.active_alerts.map((a, i) => (
                <div className="alert warn" key={i} style={{ marginBottom: '0.5rem' }}>
                  {String(a.message ?? JSON.stringify(a))}
                </div>
              ))}
            </Card>
          )}
        </>
      )}

      <div className="footer-nav">
        <button onClick={() => nav('/step/3')}>← Timeline</button>
        <button className="primary" onClick={() => nav('/review')}>
          Review everything →
        </button>
      </div>
    </div>
  );
}
