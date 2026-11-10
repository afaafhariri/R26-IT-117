import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchDashboard,
  fetchWeather,
  predictDelay,
  seedSchedule,
  submitSpi,
  updateLocation,
} from '../api/services';
import { ErrorBox, Loading, dateStr, num, pct, titleCase, toneFor } from '../components/ui';
import { LocationMap, geocodeSearch } from '../components/LocationMap';
import {
  DELAY_CATEGORIES,
  LABOUR_AVAILABILITY,
  MATERIAL_SUPPLY,
  WEATHER_SEVERITY,
} from '../types';
import type { DashboardPhase, PredictResponse, ProgressHistoryEntry, RunState, SpiResponse } from '../types';

/* Step 4, laid out after the Stitch "C04 Site Performance and Real-Time Delay
 * Monitoring" screen. The bands below are C04's own SPI thresholds
 * (pipeline/spi_calculator.py). Similar cases are shown by rank only: C04's
 * score is a vector distance, not a percentage, so the design's "94% match"
 * badges would misstate it. */

const SPI_BANDS = [
  { label: '> 0.85 nominal pace', tone: 'nominal' },
  { label: '0.70 – 0.85 warning', tone: 'review' },
  { label: '< 0.70 critical', tone: 'critical' },
] as const;

const bandFor = (spi: number) => (spi > 0.85 ? 0 : spi > 0.7 ? 1 : 2);
const chipFor = (level: string | null | undefined) =>
  ({ ok: 'nominal', warn: 'review', danger: 'critical', neutral: '' })[toneFor(level)];
const RANK_LABEL = ['Closest match', 'Second closest', 'Third closest'];

/** C04 names cases by their source file ("case_0103.txt") and its summary is
 *  the raw indexed document; show a readable title and the location only. */
function caseTitle(c: { case: string; summary?: string | null }) {
  const n = c.case.match(/(\d+)/)?.[1];
  const where = c.summary?.match(/Location\s*:\s*(.+?)\s+[A-Z][\w ]*?\s*:/)?.[1]?.trim();
  return { title: n ? `Past case ${Number(n)}` : 'Past case', where };
}

type Props = { run: RunState; update: (p: Partial<RunState>) => void };

export function Step4Performance({ run, update }: Props) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const payload = run.step3?.schedulePayload;
  const projectId = run.step4?.c04ProjectId;
  const formRef = useRef<HTMLElement>(null);

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

  /* ── site location + live weather ──
   * Both use the SAME projectId as everything else on this page (run.step4.
   * c04ProjectId) - no separate/independent project selector is introduced. */
  const weatherQuery = useQuery({
    queryKey: ['weather', projectId],
    queryFn: () => fetchWeather(projectId!),
    enabled: !!projectId,
  });

  const [locSearch, setLocSearch] = useState('');
  const [locSearchError, setLocSearchError] = useState<string | null>(null);
  const [locSearching, setLocSearching] = useState(false);
  const [locSavedAt, setLocSavedAt] = useState<Date | null>(null);

  const locationMutation = useMutation({
    mutationFn: (coords: { lat: number; lon: number }) =>
      updateLocation(projectId!, coords.lat, coords.lon),
    onSuccess: () => {
      setLocSavedAt(new Date());
      qc.invalidateQueries({ queryKey: ['dashboard', projectId] });
      qc.invalidateQueries({ queryKey: ['weather', projectId] });
    },
  });

  async function handleLocationChange(lat: number, lon: number) {
    locationMutation.mutate({ lat, lon });
  }

  async function handleLocationSearch() {
    if (!locSearch.trim()) return;
    setLocSearching(true);
    setLocSearchError(null);
    try {
      const found = await geocodeSearch(locSearch.trim());
      if (!found) {
        setLocSearchError(`No place found matching "${locSearch.trim()}".`);
        return;
      }
      await handleLocationChange(found.lat, found.lon);
    } catch (err) {
      setLocSearchError(err instanceof Error ? err.message : String(err));
    } finally {
      setLocSearching(false);
    }
  }

  /* ── progress entry ──
   * No hardcoded default: the % field starts at 0 and is only ever
   * prefilled from a phase's REAL latest recorded progress (see
   * handlePhaseChange), never a guessed/fake value. */
  const [phaseId, setPhaseId] = useState<number | ''>('');
  const [percent, setPercent] = useState(0);
  const [lastProgress, setLastProgress] = useState<ProgressHistoryEntry | null>(null);
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

  // Phases overlap, so the programme is first start → last finish, not the sum.
  const totalDays = (() => {
    if (payload.total_planned_duration_days) return payload.total_planned_duration_days;
    const t = payload.phases.flatMap((p) => [Date.parse(p.planned_start), Date.parse(p.planned_end)]).filter(Number.isFinite);
    return t.length ? Math.round((Math.max(...t) - Math.min(...t)) / 86_400_000) + 1 : 0;
  })();
  const head = (sub: string) => (
    <div className="cs-head">
      <div>
        <span className="chip ink">C04 // Site performance</span>
        <h1>Schedule performance &amp; delays</h1>
        <div className="meta">
          {[run.projectName || payload.project.name, payload.project.district, payload.project.province]
            .filter(Boolean)
            .join(' · ')}{' '}
          · {payload.project.floors} floor{payload.project.floors === 1 ? '' : 's'} · baseline {totalDays} days · {sub}
        </div>
      </div>
    </div>
  );

  /* ── not seeded yet ── */
  if (!projectId) {
    return (
      <div className="cs">
        {head('not yet monitored')}
        {seed.isError && <ErrorBox error={seed.error} onRetry={() => seed.mutate()} />}
        <section className="cs-boq">
          <header>
            <div>
              <span className="eyebrow dim">Planned baseline from the timeline</span>
              <h2>{payload.phases.length} phases ready to monitor</h2>
            </div>
          </header>
          <div className="table-wrap">
            <table className="ts-table">
              <thead>
                <tr>
                  <th>Code</th>
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
                    <td className="code">PH-{String(p.sequence).padStart(2, '0')}</td>
                    <td>
                      <b>{p.phase_group}</b>
                    </td>
                    <td className="faint">{p.sub_phase}</td>
                    <td>{dateStr(p.planned_start)}</td>
                    <td>{dateStr(p.planned_end)}</td>
                    <td className="num">{p.planned_duration_days}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <div className="cs-status">
          <div>
            <span className="eyebrow">Start monitoring</span>
            <p className="faint" style={{ margin: '0.25rem 0 0' }}>
              Loads this baseline so site progress can be scored against it. Do this once; loading it
              again creates a second copy.
            </p>
          </div>
          <div className="btn-row">
            <button className="ghost" onClick={() => nav('/step/3')}>
              ← Timeline
            </button>
            <button className="primary" onClick={() => seed.mutate()} disabled={seed.isPending}>
              {seed.isPending ? 'Loading…' : 'Load baseline into monitoring →'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ── seeded ── */
  const d = dashboard.data;
  const started = d?.phases.filter((p) => (p.actual_percent ?? 0) > 0).length ?? 0;
  // The reading the gauge shows: this session's SPI, else the newest recorded one.
  const latestHist = d?.progress_history.find((h) => h.spi_value != null) ?? null;
  const gauge = spi
    ? { spi: spi.spi_value, planned: spi.planned_percent, actual: spi.actual_percent, level: spi.alert_level, phaseId: spi.phase_id }
    : latestHist
      ? {
          spi: latestHist.spi_value!,
          planned: latestHist.planned_percent,
          actual: latestHist.actual_percent,
          level: latestHist.alert_level,
          phaseId: latestHist.phase_id,
        }
      : null;
  const gaugePhase = gauge ? d?.phases.find((p) => p.phase_id === gauge.phaseId) : undefined;
  const lastPrediction = prediction ?? [...(run.step4?.entries ?? [])].reverse().find((e) => e.prediction)?.prediction ?? null;
  const actions = lastPrediction
    ? Array.isArray(lastPrediction.recommendation?.corrective_actions)
      ? lastPrediction.recommendation.corrective_actions
      : lastPrediction.recommendation?.corrective_actions
        ? [lastPrediction.recommendation.corrective_actions]
        : []
    : [];
  const w = weatherQuery.data?.weather;
  const code = (p: DashboardPhase) => `PH-${String(p.sequence).padStart(2, '0')}`;

  return (
    <div className="cs">
      {head(`${started} of ${d?.phases.length ?? payload.phases.length} phases started`)}

      <div className="btn-row" style={{ marginTop: '-0.75rem' }}>
        {gauge && (
          <span className={`chip ${chipFor(gauge.level)}`}>
            SPI health: <b>{titleCase(String(gauge.level ?? '—'))} ({num(gauge.spi, 2)})</b>
          </span>
        )}
        <span className="chip">
          Active alerts: <b>{d?.active_alerts.length ?? 0}</b>
        </span>
        <span style={{ flex: 1 }} />
        <button className="sm" onClick={() => dashboard.refetch()} disabled={dashboard.isFetching}>
          {dashboard.isFetching ? 'Refreshing…' : 'Re-calculate view'}
        </button>
        <button className="sm" onClick={() => formRef.current?.scrollIntoView({ behavior: 'smooth' })}>
          + Log progress update
        </button>
      </div>

      {dashboard.isPending && <Loading what="Loading site performance" />}
      {dashboard.isError && <ErrorBox error={dashboard.error} onRetry={() => dashboard.refetch()} />}

      {d && (
        <>
          <div className="cs-layers">
            <div className="cs-layer">
              <div className="between">
                <span className="eyebrow dim">Stage 01 // SPI monitor</span>
                {gauge && <span className={`chip ${chipFor(gauge.level)}`}>{titleCase(String(gauge.level))}</span>}
              </div>
              <h3>Schedule performance index</h3>
              <p>
                {gauge
                  ? `Actual ${num(gauge.actual)}% against planned ${num(gauge.planned)}%: SPI ${num(gauge.spi, 2)}.`
                  : 'Record progress on a phase to score it against the plan.'}
              </p>
            </div>
            <div className="cs-layer">
              <div className="between">
                <span className="eyebrow dim">Stage 02 // Delay risk</span>
                <span className="chip">XGBoost</span>
              </div>
              <h3>Delay risk model</h3>
              <p>
                {lastPrediction
                  ? `${titleCase(lastPrediction.prediction.delay_risk)} risk, about ${lastPrediction.prediction.estimated_delay_days} days of slippage.`
                  : 'Runs when a phase scores warning or critical.'}
              </p>
            </div>
            <div className="cs-layer">
              <div className="between">
                <span className="eyebrow dim">Stage 03 // Case retrieval</span>
                <span className="chip">FAISS</span>
              </div>
              <h3>Similar delay cases</h3>
              <p>
                {lastPrediction
                  ? `${lastPrediction.similar_cases.length} comparable past cases retrieved.`
                  : 'Finds past Sri Lankan delays most like this one.'}
              </p>
            </div>
            <div className="cs-layer hot">
              <div className="between">
                <span className="eyebrow">Stage 04 // Actions</span>
                <span className="chip critical">Gemini</span>
              </div>
              <h3>Corrective directives</h3>
              <p>
                {lastPrediction
                  ? `${actions.length} recommended action${actions.length === 1 ? '' : 's'} for the site team.`
                  : 'Drafts actions grounded in the retrieved cases.'}
              </p>
            </div>
          </div>

          <div className="cs-main">
            <section className="cs-panel">
              <div className="between">
                <span className="eyebrow dim">Real-time performance gauge</span>
                {gauge && (
                  <span className={`chip ${chipFor(gauge.level)}`}>
                    {titleCase(String(gauge.level))} ({SPI_BANDS[bandFor(gauge.spi)].label.split(' ').slice(0, 2).join(' ')})
                  </span>
                )}
              </div>
              {gauge ? (
                <>
                  <div className="pf-gauge">
                    <div>
                      <span className="eyebrow dim">Current schedule performance index</span>
                      <div className="ts-big">
                        {num(gauge.spi, 2)}
                        <span>SPI</span>
                      </div>
                      {gaugePhase && <span className="faint">{gaugePhase.phase_group} · {gaugePhase.sub_phase}</span>}
                    </div>
                    <div className="pf-cells">
                      <div>
                        <span className="eyebrow dim">Actual progress</span>
                        <b>{num(gauge.actual)}%</b>
                      </div>
                      <div>
                        <span className="eyebrow dim">Planned baseline</span>
                        <b>{num(gauge.planned)}%</b>
                      </div>
                      <div>
                        <span className="eyebrow dim">Schedule variance</span>
                        <b className={gauge.actual - gauge.planned < 0 ? 'terra' : ''}>
                          {gauge.actual - gauge.planned >= 0 ? '+' : '−'}
                          {num(Math.abs(gauge.actual - gauge.planned))} pts
                        </b>
                      </div>
                    </div>
                  </div>
                  <div className="pf-scale" aria-hidden>
                    <span style={{ left: `${Math.min(100, Math.max(0, (gauge.spi / 1.2) * 100))}%` }} />
                  </div>
                </>
              ) : (
                <p className="faint" style={{ margin: '1rem 0' }}>
                  Nothing recorded yet. Every phase reads “not started” until you log progress below,
                  and that is also what feeds the delay model.
                </p>
              )}
              <div className="pf-bands">
                {SPI_BANDS.map((b, i) => (
                  <span key={b.label} className={`chip ${b.tone}${gauge && bandFor(gauge.spi) === i ? ' on' : ''}`}>
                    {b.label}
                  </span>
                ))}
              </div>
            </section>

            <section className="cs-panel">
              <div className="between">
                <span className="eyebrow dim">Diagnostics &amp; site weather</span>
                <button className="ghost sm" onClick={() => weatherQuery.refetch()} disabled={weatherQuery.isFetching}>
                  {weatherQuery.isFetching ? 'Refreshing…' : 'Refresh'}
                </button>
              </div>
              {lastPrediction?.recommendation?.explanation && (
                <div className="pf-cause">
                  <span className="eyebrow">Primary root cause identified</span>
                  <p>{lastPrediction.recommendation.explanation}</p>
                </div>
              )}
              {weatherQuery.isPending && <Loading what="Fetching current weather" />}
              {weatherQuery.isError && <ErrorBox error={weatherQuery.error} onRetry={() => weatherQuery.refetch()} />}
              {w && (
                <>
                  <div className="pf-weather">
                    <div>
                      <span className="eyebrow dim">Rainfall</span>
                      <b>{w.rainfall_mm != null ? `${num(w.rainfall_mm)} mm` : '—'}</b>
                    </div>
                    <div>
                      <span className="eyebrow dim">Temperature</span>
                      <b>{w.temperature_c != null ? `${num(w.temperature_c)}°C` : '—'}</b>
                    </div>
                    <div>
                      <span className="eyebrow dim">Wind</span>
                      <b>{w.wind_mps != null ? `${num(w.wind_mps)} m/s` : '—'}</b>
                    </div>
                  </div>
                  <div className="between" style={{ marginTop: '0.75rem' }}>
                    <span className={`chip ${chipFor(w.weather_severity)}`}>
                      Severity: <b>{w.weather_severity ?? 'Unknown'}</b>
                    </span>
                    <span className="faint">{w.condition ?? ''}</span>
                  </div>
                  <p className="faint" style={{ margin: '0.6rem 0 0' }}>
                    {w.source === 'live' ? 'Live reading' : 'Fallback value — no live reading available'}
                    {' · '}
                    {w.location_source === 'coordinates'
                      ? 'at the pinned site'
                      : 'for the district — pin the exact site below for a closer reading'}
                    . Severity is an input to the delay model.
                  </p>
                  {w.error && <p className="faint" style={{ color: 'var(--danger)', margin: '0.35rem 0 0' }}>{w.error}</p>}
                </>
              )}
              {lastPrediction && (
                <div className="pf-prob">
                  <div className="between">
                    <span className="eyebrow dim">Delay probability</span>
                    <b className="terra">
                      {titleCase(lastPrediction.prediction.delay_risk)} · {pct(lastPrediction.prediction.confidence)}
                    </b>
                  </div>
                  {Object.entries(lastPrediction.prediction.risk_probabilities ?? {}).map(([k, v]) => (
                    <div className="pf-prob-row" key={k}>
                      <span>{titleCase(k)}</span>
                      <div className="track">
                        <span style={{ width: `${(v <= 1 ? v : v / 100) * 100}%` }} />
                      </div>
                      <span className="tnum">{pct(v)}</span>
                    </div>
                  ))}
                  <span className="faint">
                    Estimated slippage: <b>{lastPrediction.prediction.estimated_delay_days} days</b>
                  </span>
                </div>
              )}
            </section>
          </div>

          <section className="cs-boq">
            <header>
              <div>
                <span className="eyebrow dim">Execution schedule drill-down</span>
                <h2>{d.phases.length}-phase SPI performance matrix</h2>
              </div>
              <span className="chip">
               Total baseline: <b>{d.project_summary?.total_duration_days ?? totalDays} days</b>
              </span>
            </header>
            <div className="table-wrap">
              <table className="ts-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Phase &amp; scope</th>
                    <th>Planned</th>
                    <th className="num">Days</th>
                    <th className="num">Planned %</th>
                    <th className="num">Actual %</th>
                    <th className="num">SPI</th>
                    <th>Status</th>
                    <th className="pf-bar-col">Progress</th>
                  </tr>
                </thead>
                <tbody>
                  {d.phases.map((p) => {
                    // Prefer the latest SPI verdict; `status` stays NOT_STARTED until work is logged above 0%.
                    const level = p.latest_spi?.alert_level ?? p.status;
                    const crit = toneFor(level) === 'danger';
                    const actual = p.actual_percent ?? 0;
                    return (
                      <tr key={p.phase_id} className={crit ? 'crit' : ''}>
                        <td className="code">{code(p)}</td>
                        <td>
                          <b>{p.phase_group}</b>
                          <div className="faint">{p.sub_phase}</div>
                        </td>
                        <td className="faint">
                          {dateStr(p.planned_start)} → {dateStr(p.planned_end)}
                        </td>
                        <td className="num">{p.planned_duration_days ?? '—'}</td>
                        <td className="num">{num(p.expected_progress_percent)}%</td>
                        <td className="num">{p.actual_percent == null ? '—' : `${num(p.actual_percent)}%`}</td>
                        <td className="num">{p.latest_spi == null ? '—' : num(p.latest_spi.spi_value, 2)}</td>
                        <td>
                          <span className={`chip ${chipFor(level)}`}>{titleCase(level)}</span>
                        </td>
                        <td className="pf-bar-col">
                          <div className="pf-progress">
                            <span className="exp" style={{ width: `${Math.min(100, p.expected_progress_percent)}%` }} />
                            <span className={`act ${chipFor(level)}`} style={{ width: `${Math.min(100, actual)}%` }} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <footer>
              <span>Bar: shaded = where the phase should be today, solid = recorded progress.</span>
            </footer>
          </section>

          <section className="cs-panel" ref={formRef}>
            <div className="between" style={{ marginBottom: '1rem' }}>
              <span className="eyebrow">Log progress update</span>
              <span className="eyebrow dim">Step 1 of 2 — schedule performance index</span>
            </div>
            <div className="grid cols-3">
              <label className="field">
                Phase
                <select
                  value={phaseId}
                  onChange={(e) => {
                    const nextPhaseId = e.target.value ? Number(e.target.value) : '';
                    setPhaseId(nextPhaseId);
                    setSpi(null);
                    setPrediction(null);

                    // Prefill from this phase's REAL latest recorded progress
                    // (backend already returns progress_history newest-first).
                    // 0% only when nothing has ever been recorded for it -
                    // never a guessed/hardcoded starting value.
                    const latest =
                      nextPhaseId === ''
                        ? null
                        : (d.progress_history.find((h) => h.phase_id === nextPhaseId) ?? null);
                    setLastProgress(latest);
                    setPercent(latest ? latest.actual_percent : 0);
                  }}
                >
                  <option value="">Select a phase…</option>
                  {d.phases.map((p) => (
                    <option key={p.phase_id} value={p.phase_id}>
                      {code(p)} · {p.phase_group} — {p.sub_phase}
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
                <span className="faint">
                  {phaseId === ''
                    ? 'Select a phase to see its last recorded progress.'
                    : lastProgress
                      ? `Last recorded: ${num(lastProgress.actual_percent)}% on ${dateStr(lastProgress.update_date)}. Edit if it has changed.`
                      : 'No progress recorded for this phase yet — starting at 0%.'}
                </span>
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
              <div className={`cs-notice${spi.requires_prediction_step ? ' warn' : ''}`} style={{ marginTop: '1rem' }}>
                <svg viewBox="0 0 20 20" aria-hidden>
                  <circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
                  {spi.requires_prediction_step ? (
                    <path d="M10 5.5v5.5M10 13.4v1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
                  ) : (
                    <path d="m6.3 10.2 2.5 2.5 4.9-5.1" fill="none" stroke="currentColor" strokeWidth="1.6" />
                  )}
                </svg>
                <div>
                  <b>
                    SPI {num(spi.spi_value, 2)} · {titleCase(spi.alert_level)}
                  </b>
                  <p>
                    {num(spi.actual_percent)}% done against {num(spi.planned_percent)}% planned.{' '}
                    {spi.requires_prediction_step
                      ? 'Behind schedule — run the delay prediction below.'
                      : 'On track — no delay prediction needed.'}
                  </p>
                </div>
              </div>
            )}
          </section>

          {spi?.requires_prediction_step && (
            <section className="cs-panel">
              <div className="between" style={{ marginBottom: '1rem' }}>
                <span className="eyebrow">Predict delay</span>
                <span className="eyebrow dim">Step 2 of 2 — site conditions for the model</span>
              </div>
              <div className="grid cols-4">
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
                  <select value={weather} onChange={(e) => setWeather(e.target.value)}>
                    <option value="">Use the live reading</option>
                    {WEATHER_SEVERITY.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="cs-status">
                <span className="faint">Scores the delay, finds similar past cases and drafts actions.</span>
                <button className="accent" onClick={() => predictMutation.mutate()} disabled={predictMutation.isPending}>
                  {predictMutation.isPending ? 'Predicting…' : 'Predict delay & draft actions →'}
                </button>
              </div>
              {predictMutation.isError && <ErrorBox error={predictMutation.error} />}
            </section>
          )}

          {lastPrediction && lastPrediction.similar_cases.length > 0 && (
            <section className="cs-panel">
              <div className="between">
                <div>
                  <span className="eyebrow dim">Similar-case search</span>
                  <h2 style={{ marginTop: '0.4rem' }}>Top {lastPrediction.similar_cases.length} delay case analogues</h2>
                </div>
                <span className="chip">Ranked by similarity</span>
              </div>
              <div className="pf-cases">
                {lastPrediction.similar_cases.map((c) => {
                  const t = caseTitle(c);
                  return (
                  <article key={c.rank}>
                    <div className="between">
                      <span className="eyebrow dim">Case {c.rank}</span>
                      <span className="chip nominal">{RANK_LABEL[c.rank - 1] ?? `Rank ${c.rank}`}</span>
                    </div>
                    <h3>{t.title}</h3>
                    {t.where && <p className="faint">{t.where}</p>}
                    {c.cause_of_delay && (
                      <p>
                        <b>Root cause: </b>
                        {c.cause_of_delay}
                      </p>
                    )}
                    {c.construction_status && <p className="terra">Outcome: {c.construction_status}</p>}
                    {c.corrective_action_taken && (
                      <div className="pf-fix">
                        <span className="eyebrow dim">Field solution executed</span>
                        <p>{c.corrective_action_taken}</p>
                      </div>
                    )}
                  </article>
                  );
                })}
              </div>
            </section>
          )}

          {lastPrediction && actions.length > 0 && (
            <section className="cs-panel pf-directives">
              <span className="eyebrow">Grounded in the retrieved cases</span>
              <h2 style={{ margin: '0.4rem 0 1rem' }}>Synthesised field mitigation directives</h2>
              <div className="pf-directive-grid">
                {actions.map((a, i) => (
                  <article key={i}>
                    <span className="eyebrow">Directive {String(i + 1).padStart(2, '0')}</span>
                    <p>{a}</p>
                  </article>
                ))}
              </div>
              <div className="pf-target">
                <span className="eyebrow dim">Predicted impact</span>
                <h3>
                  {titleCase(lastPrediction.prediction.delay_risk)} delay risk ·{' '}
                  <span className="terra">about {lastPrediction.prediction.estimated_delay_days} days</span>
                </h3>
                {lastPrediction.weather_used?.weather_severity && (
                  <p className="faint">
                    Weather used: {lastPrediction.weather_used.weather_severity}
                    {lastPrediction.weather_used.source ? ` (${lastPrediction.weather_used.source})` : ''}
                    {lastPrediction.weather_used.temperature_c != null && ` · ${lastPrediction.weather_used.temperature_c}°C`}
                  </p>
                )}
              </div>
            </section>
          )}

          <section className="cs-panel">
            <div className="between">
              <span className="eyebrow dim">Site location</span>
              <span className="faint">
                {d.project.latitude != null && d.project.longitude != null
                  ? `${num(d.project.latitude, 4)}, ${num(d.project.longitude, 4)}`
                  : 'Not pinned yet'}
              </span>
            </div>
            <p className="faint" style={{ margin: '0.5rem 0' }}>
              Click the map or drag the pin to set the exact site. It saves automatically and is what
              the weather reading, and so the delay model, uses.
            </p>
            <div className="row" style={{ marginBottom: '0.5rem' }}>
              <input
                type="text"
                placeholder="Search a place, e.g. Galle, Sri Lanka"
                value={locSearch}
                onChange={(e) => setLocSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleLocationSearch();
                  }
                }}
                style={{ flex: 1 }}
              />
              <button type="button" onClick={handleLocationSearch} disabled={locSearching || !locSearch.trim()}>
                {locSearching ? 'Searching…' : 'Find on map'}
              </button>
            </div>
            {locSearchError && <div className="faint" style={{ color: 'var(--danger)' }}>{locSearchError}</div>}
            <LocationMap latitude={d.project.latitude} longitude={d.project.longitude} onChange={handleLocationChange} />
            <div className="faint" style={{ marginTop: '0.5rem' }}>
              {locationMutation.isPending && 'Saving location…'}
              {!locationMutation.isPending && locationMutation.isError && <ErrorBox error={locationMutation.error} />}
              {!locationMutation.isPending && !locationMutation.isError && locSavedAt && (
                <>Location saved at {locSavedAt.toLocaleTimeString()}.</>
              )}
            </div>
          </section>

          {d.active_alerts.length > 0 && (
            <section className="cs-panel">
              <span className="eyebrow">Active alerts</span>
              <div className="stack" style={{ marginTop: '0.75rem', gap: '0.5rem' }}>
                {d.active_alerts.map((a, i) => (
                  <div className="cs-notice warn" key={i}>
                    <svg viewBox="0 0 20 20" aria-hidden>
                      <circle cx="10" cy="10" r="8.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M10 5.5v5.5M10 13.4v1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
                    </svg>
                    <div>
                      <b>{a.alert_type ? titleCase(String(a.alert_type)) : 'Alert'}</b>
                      <p>{a.message ? String(a.message) : 'A phase needs attention.'}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      <div className="cs-status">
        <div className="chips">
          <span className="chip">
            <span className="dot" /> Thresholds: <b>0.85 warning · 0.70 critical</b>
          </span>
          <span className="chip">
            Weather: <b>{w ? (w.source === 'live' ? 'Live' : 'Fallback') : '—'}</b>
          </span>
        </div>
        <div className="btn-row">
          <button className="ghost" onClick={() => nav('/step/3')}>
            ← Timeline
          </button>
          <button className="primary" onClick={() => nav('/review')}>
            Review everything →
          </button>
        </div>
      </div>
    </div>
  );
}
