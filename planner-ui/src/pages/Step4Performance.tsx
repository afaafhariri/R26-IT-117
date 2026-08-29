import { useState } from 'react';
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
import { Badge, Card, ErrorBox, Loading, Stat, dateStr, num, pct, titleCase, toneFor } from '../components/ui';
import { LocationMap, geocodeSearch } from '../components/LocationMap';
import {
  DELAY_CATEGORIES,
  LABOUR_AVAILABILITY,
  MATERIAL_SUPPLY,
  WEATHER_SEVERITY,
} from '../types';
import type { PredictResponse, ProgressHistoryEntry, RunState, SpiResponse } from '../types';

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

          <div className="grid cols-2">
            <Card
              title="Site location"
              subtitle={
                d.project.latitude != null && d.project.longitude != null
                  ? `${num(d.project.latitude, 4)}, ${num(d.project.longitude, 4)}`
                  : 'Not pinned yet'
              }
            >
              <p className="faint">
                Click the map or drag the pin to set the exact site. This saves automatically and is
                what the weather lookup (and the delay model) uses.
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
                <button
                  className="ghost"
                  type="button"
                  onClick={handleLocationSearch}
                  disabled={locSearching || !locSearch.trim()}
                >
                  {locSearching ? 'Searching…' : 'Find on map'}
                </button>
              </div>
              {locSearchError && <div className="hint" style={{ color: 'var(--danger, #b91c1c)' }}>{locSearchError}</div>}
              <LocationMap
                latitude={d.project.latitude}
                longitude={d.project.longitude}
                onChange={handleLocationChange}
              />
              <div className="faint" style={{ marginTop: '0.5rem' }}>
                {locationMutation.isPending && 'Saving location…'}
                {!locationMutation.isPending && locationMutation.isError && (
                  <ErrorBox error={locationMutation.error} />
                )}
                {!locationMutation.isPending && !locationMutation.isError && locSavedAt && (
                  <>Location saved at {locSavedAt.toLocaleTimeString()}.</>
                )}
              </div>
            </Card>

            <Card title="Weather at the site" actions={
              <button className="ghost" onClick={() => weatherQuery.refetch()} disabled={weatherQuery.isFetching}>
                {weatherQuery.isFetching ? 'Refreshing…' : 'Refresh'}
              </button>
            }>
              {weatherQuery.isPending && <Loading what="Fetching current weather" />}
              {weatherQuery.isError && <ErrorBox error={weatherQuery.error} onRetry={() => weatherQuery.refetch()} />}
              {weatherQuery.data && (
                <>
                  <div className="row" style={{ marginBottom: '0.75rem' }}>
                    <Badge tone={toneFor(weatherQuery.data.weather.weather_severity)}>
                      {weatherQuery.data.weather.weather_severity ?? 'Unknown'}
                    </Badge>
                    <span className="faint">
                      This severity is an actual input to the delay-risk model, not just a display value.
                    </span>
                  </div>
                  <div className="grid cols-4">
                    <Stat
                      label="Temperature"
                      value={
                        weatherQuery.data.weather.temperature_c != null
                          ? `${num(weatherQuery.data.weather.temperature_c)}°C`
                          : '—'
                      }
                    />
                    <Stat label="Condition" value={weatherQuery.data.weather.condition ?? '—'} />
                    <Stat
                      label="Rainfall"
                      value={
                        weatherQuery.data.weather.rainfall_mm != null
                          ? `${num(weatherQuery.data.weather.rainfall_mm)} mm`
                          : '—'
                      }
                    />
                    <Stat
                      label="Wind"
                      value={
                        weatherQuery.data.weather.wind_mps != null
                          ? `${num(weatherQuery.data.weather.wind_mps)} m/s`
                          : '—'
                      }
                    />
                  </div>
                  <div className="faint" style={{ marginTop: '0.75rem' }}>
                    {weatherQuery.data.weather.source === 'live' ? 'Live reading' : 'Fallback value (no live reading available)'}
                    {' · '}
                    {weatherQuery.data.weather.location_source === 'coordinates'
                      ? 'based on the exact site coordinates'
                      : 'based on district name — pin the exact site above for a more accurate reading'}
                    {weatherQuery.dataUpdatedAt ? ` · Last updated ${new Date(weatherQuery.dataUpdatedAt).toLocaleTimeString()}` : ''}
                  </div>
                  {weatherQuery.data.weather.error && (
                    <div className="hint" style={{ color: 'var(--danger, #b91c1c)', marginTop: '0.35rem' }}>
                      {weatherQuery.data.weather.error}
                    </div>
                  )}
                </>
              )}
            </Card>
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
                <span className="faint">
                  {phaseId === ''
                    ? 'Select a phase to see its last recorded progress.'
                    : lastProgress
                      ? `Last recorded: ${num(lastProgress.actual_percent)}% on ${dateStr(lastProgress.update_date)}${
                          lastProgress.entered_by ? ` by ${lastProgress.entered_by}` : ''
                        }. Edit if it has changed.`
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
                    <span className="title">On track — no delay prediction needed.</span>
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
                  {prediction.similar_cases && prediction.similar_cases.length > 0 && (
                    <>
                      <hr className="divider" />
                      <h3>Similar historical cases</h3>
                      <p className="faint">
                        The closest past construction-delay cases retrieved for this situation.
                        Distance is a similarity metric — lower means more similar, not a percentage.
                      </p>
                      <div className="grid cols-3">
                        {prediction.similar_cases.map((c) => (
                          <div key={c.rank} className="card" style={{ padding: '0.75rem' }}>
                            <div className="between">
                              <strong>Rank {c.rank}</strong>
                              <span className="mono faint">{c.case}</span>
                            </div>
                            {c.cause_of_delay && (
                              <p className="hint">
                                <strong>Cause: </strong>
                                {c.cause_of_delay}
                              </p>
                            )}
                            {c.corrective_action_taken && (
                              <p className="hint">
                                <strong>What they did: </strong>
                                {c.corrective_action_taken}
                              </p>
                            )}
                            {c.construction_status && (
                              <p className="hint">
                                <strong>Outcome: </strong>
                                {c.construction_status}
                              </p>
                            )}
                            <div className="faint" style={{ marginTop: '0.4rem' }}>
                              Distance: {num(c.score, 4)} (lower = more similar)
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                  {prediction.recommendation?.explanation && (
                    <>
                      <hr className="divider" />
                      <h3>Recommendation</h3>
                      <p className="muted">{prediction.recommendation.explanation}</p>
                      {Array.isArray(prediction.recommendation.corrective_actions) &&
                        prediction.recommendation.corrective_actions.length > 0 && (
                          <ul>
                            {prediction.recommendation.corrective_actions.map((a, i) => (
                              <li key={i}>{a}</li>
                            ))}
                          </ul>
                        )}
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
