import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { post } from '../api/client';
import { ErrorBox, dateStr, num, pct, titleCase } from '../components/ui';
import type { CostReport, RunState, TimelineResponse } from '../types';

/* Step 3, laid out after the Stitch "C03 Timeline and CPM Schedule
 * Optimisation" screen. Every figure comes from C03's predict response. The
 * design's float column, per-epoch loss curve and JSON handoff panel have no
 * counterpart in that response (or are internals), so they are not drawn. */

type Props = { run: RunState; update: (p: Partial<RunState>) => void };
type ScopeType = 'full_construction' | 'partial_construction';

interface ConstructionScope {
  planned_total_floors: number;
  timeline_required_floors: number;
  scope_type: ScopeType;
  scope_description: string;
}

interface PredictionArgs {
  start: string;
  scope: ConstructionScope;
}

const DEFAULT_SCOPE_DESCRIPTION = 'Customer wants to construct only ground floor at this stage';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function readPositiveNumber(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

function inferPlannedFloors(run: RunState, estimateReport: CostReport | undefined): number {
  const designFloors = readPositiveNumber(run.step1?.buildingSchema.floors, 0);
  if (designFloors > 0) return designFloors;

  const feed = asRecord(estimateReport?.feeds_downstream);
  const metadata = asRecord(estimateReport?.model_metadata);
  return readPositiveNumber(feed.floors ?? feed.number_of_floors ?? metadata.floors, 1);
}

function scopeTypeFor(plannedTotalFloors: number, timelineRequiredFloors: number): ScopeType {
  return timelineRequiredFloors >= plannedTotalFloors ? 'full_construction' : 'partial_construction';
}

function scopeValidation(plannedTotalFloors: number, timelineRequiredFloors: number): string | null {
  if (plannedTotalFloors < 1) return 'Planned total floors must be at least 1.';
  if (timelineRequiredFloors < 1) return 'Timeline required floors must be at least 1.';
  if (timelineRequiredFloors > plannedTotalFloors) {
    return 'Timeline required floors cannot exceed planned total floors.';
  }
  return null;
}

function buildTimelineBody(
  estimateReport: CostReport,
  run: RunState,
  start: string,
  scope: ConstructionScope,
) {
  return {
    project_id: run.runId,
    project_name: run.projectName,
    planned_start_date: start,
    location: estimateReport.rate_metadata.district || 'Colombo',
    building_type: 'residential',
    rate_metadata: estimateReport.rate_metadata,
    feeds_downstream: estimateReport.feeds_downstream,
    total_estimated_cost: estimateReport.summary.total_lkr,
    construction_scope: scope,
  };
}

function predictTimelineWithScope(
  estimateReport: CostReport,
  run: RunState,
  start: string,
  scope: ConstructionScope,
) {
  return post<TimelineResponse>(
    'c03',
    '/api/timeline/predict',
    buildTimelineBody(estimateReport, run, start, scope),
  );
}

function stageExplanation(task: string): string {
  const key = task.toLowerCase().replace(/[_-]+/g, ' ');
  if (key.includes('foundation')) return 'Foundation work will be completed during this period.';
  if (key.includes('structure') || key.includes('column') || key.includes('beam')) {
    return 'Columns, beams, and slab work will be completed.';
  }
  if (key.includes('masonry')) return 'Wall construction work will be completed.';
  if (key.includes('roof')) return 'Roof or roof slab work will be completed.';
  if (key.includes('electrical')) {
    return 'Electrical conduit and wiring preparation work will be completed.';
  }
  if (key.includes('plumbing')) return 'Plumbing and drainage work will be completed.';
  if (key.includes('plaster')) return 'Wall plastering work will be completed.';
  if (key.includes('finish') || key.includes('tiling')) {
    return 'Tiling and finishing work will be completed.';
  }
  if (key.includes('painting') || key.includes('paint')) return 'Painting work will be completed.';
  if (key.includes('external')) return 'External construction work will be completed.';
  if (key.includes('handover')) return 'Final handover to customer.';
  return 'This construction activity will be carried out according to the planned schedule.';
}

function durationLabel(task: { duration_days: number | null; duration_weeks: number }) {
  if (task.duration_days !== null && task.duration_days !== undefined) {
    return `${task.duration_days} days`;
  }
  return `${num(task.duration_weeks)} weeks`;
}

function taskKey(value: string): string {
  return value.toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function isCriticalTask(taskName: string, criticalPath: string[]): boolean {
  const name = taskKey(taskName);
  return criticalPath.some((critical) => {
    const key = taskKey(critical);
    return key === name || key.includes(name) || name.includes(key);
  });
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (Array.isArray(value)) return value.length > 0 ? value.map(String).join(', ') : '—';
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return '—';
    return entries.map(([key, val]) => `${titleCase(key)}: ${formatValue(val)}`).join('; ');
  }
  return String(value);
}

function isEquipmentKey(key: string): boolean {
  const k = key.toLowerCase();
  return (
    k.includes('equipment') ||
    k.includes('resource') ||
    k.includes('tool') ||
    k.includes('machine') ||
    k.includes('plant')
  );
}

function isNoteKey(key: string): boolean {
  const k = key.toLowerCase();
  return k.includes('duration') || k.includes('note') || k.includes('remark') || k.includes('comment');
}

function resourceRows(plan: TimelineResponse['resource_allocation_plan']) {
  return Object.entries(plan ?? {}).map(([stage, raw]) => {
    const data = asRecord(raw);
    const equipment = Object.entries(data)
      .filter(([key]) => isEquipmentKey(key))
      .map(([, value]) => formatValue(value))
      .filter((value) => value !== '—')
      .join(', ');
    const notes = Object.entries(data)
      .filter(([key]) => isNoteKey(key))
      .map(([key, value]) => `${titleCase(key)}: ${formatValue(value)}`)
      .join('; ');
    const labourEntries = Object.entries(data).filter(
      ([key]) => !isEquipmentKey(key) && !isNoteKey(key),
    );
    const numericWorkers = labourEntries
      .map(([, value]) => Number(value))
      .filter((value) => Number.isFinite(value));
    const workers =
      numericWorkers.length > 0
        ? numericWorkers.reduce((sum, value) => sum + value, 0)
        : data.workers ?? data.worker_count ?? data.total_workers;

    return {
      stage,
      crew:
        labourEntries.length > 0
          ? labourEntries.map(([key, value]) => `${titleCase(key)}: ${formatValue(value)}`).join(', ')
          : '—',
      workers: formatValue(workers),
      equipment: equipment || '—',
      notes: notes || '—',
    };
  });
}

/** One colour per phase, cycling the design's four pigments. */
const PHASE_TONES = ['var(--ink)', 'var(--terra)', 'var(--accent)', 'var(--ochre)', '#6d8ea6', '#5b6470'];

type Filter = 'all' | 'critical' | 'other';

function downloadSchedule(timeline: TimelineResponse, codes: Map<string, string>, critical: (t: string) => boolean) {
  const deps = new Map((timeline.task_dependencies ?? []).map((d) => [taskKey(d.task), d.depends_on]));
  const rows = [
    ['Code', 'Phase', 'Predecessors', 'Start date', 'End date', 'Start week', 'End week', 'Duration (days)', 'Critical'],
    ...(timeline.gantt_chart_data ?? []).map((t) => [
      codes.get(taskKey(t.task)) ?? '',
      titleCase(t.task),
      (deps.get(taskKey(t.task)) ?? []).map((d) => codes.get(taskKey(d)) ?? titleCase(d)).join(' '),
      t.start_date ?? '',
      t.end_date ?? '',
      String(t.start_week),
      String(t.end_week),
      String(t.duration_days ?? ''),
      critical(t.task) ? 'Yes' : 'No',
    ]),
  ];
  const csv = rows.map((r) => r.map((c) => (/[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `programme-${(timeline.project_name || 'plan').replace(/[^\w-]+/g, '-').toLowerCase()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function Step3Timeline({ run, update }: Props) {
  const nav = useNavigate();
  const estimateReport = run.step2?.estimate;
  const initialFloors = inferPlannedFloors(run, estimateReport);

  const [startDate, setStartDate] = useState(
    run.step3?.schedulePayload?.planned_start_date ?? new Date().toISOString().slice(0, 10),
  );
  const [timeline, setTimeline] = useState<TimelineResponse | undefined>();
  const plannedTotalFloors = initialFloors;
  const [timelineRequiredFloors, setTimelineRequiredFloors] = useState(
    Math.min(initialFloors, 1),
  );
  const [scopeDescription, setScopeDescription] = useState(DEFAULT_SCOPE_DESCRIPTION);
  const [filter, setFilter] = useState<Filter>('all');

  const scopeType = scopeTypeFor(plannedTotalFloors, timelineRequiredFloors);
  const scopeError = scopeValidation(plannedTotalFloors, timelineRequiredFloors);
  const constructionScope = useMemo<ConstructionScope>(
    () => ({
      planned_total_floors: plannedTotalFloors,
      timeline_required_floors: timelineRequiredFloors,
      scope_type: scopeType,
      scope_description: scopeDescription.trim() || DEFAULT_SCOPE_DESCRIPTION,
    }),
    [plannedTotalFloors, scopeDescription, scopeType, timelineRequiredFloors],
  );

  const predict = useMutation({
    mutationFn: ({ start, scope }: PredictionArgs) =>
      predictTimelineWithScope(estimateReport!, run, start, scope),
    onMutate: () => {
      setTimeline(undefined);
    },
    onSuccess: (t) => {
      setTimeline(t);
      // The predict response already carries the exact body C04 wants.
      if (t.performance_monitoring_payload) {
        update({
          step3: { timeline: t, schedulePayload: t.performance_monitoring_payload },
          step4: undefined,
        });
      }
    },
  });

  const phases = useMemo(
    () => Object.entries(timeline?.predicted_phase_durations_weeks ?? {}),
    [timeline],
  );

  if (!estimateReport) {
    return (
      <div className="alert warn">
        No cost estimate yet. <Link to="/step/2">Go back to step 2</Link>.
      </div>
    );
  }

  const noPayload = timeline && !timeline.performance_monitoring_payload;
  const runPrediction = () => {
    if (scopeError) return;
    predict.mutate({ start: startDate, scope: constructionScope });
  };
  const scopeSummary = asRecord(
    timeline?.construction_scope_summary ?? timeline?.input_summary?.construction_scope_summary,
  );

  const tasks = timeline?.gantt_chart_data ?? [];
  const criticalPath = timeline?.critical_path ?? [];
  const isCrit = (name: string) => isCriticalTask(name, criticalPath);
  const codes = new Map(tasks.map((t, i) => [taskKey(t.task), `PH-${String(i + 1).padStart(2, '0')}`]));
  const deps = new Map((timeline?.task_dependencies ?? []).map((d) => [taskKey(d.task), d.depends_on]));
  const totalWeeks = timeline?.total_project_duration_weeks ?? 0;
  const span = Math.max(totalWeeks, ...tasks.map((t) => t.end_week - 1), 1);
  const critTasks = tasks.filter((t) => isCrit(t.task));
  const otherTasks = tasks.filter((t) => !isCrit(t.task));
  const critWeeks = critTasks.reduce((a, t) => a + t.duration_weeks, 0);
  const critRatio = totalWeeks > 0 ? Math.min(1, critWeeks / totalWeeks) : 0;
  const mp = timeline?.model_predictions;
  const lstmWeeks = mp?.lstm_predicted_total_duration_weeks;
  const phaseWeeksTotal = phases.reduce((a, [, w]) => a + w, 0);
  const crews = resourceRows(timeline?.resource_allocation_plan ?? {});
  const peakCrew = (() => {
    const peak = new Map<string, number>();
    for (const raw of Object.values(timeline?.resource_allocation_plan ?? {})) {
      for (const [k, v] of Object.entries(asRecord(raw))) {
        const n = Number(v);
        if (Number.isFinite(n) && !isEquipmentKey(k)) peak.set(k, Math.max(peak.get(k) ?? 0, n));
      }
    }
    return [...peak.entries()].sort((a, b) => b[1] - a[1]);
  })();
  const shown = filter === 'all' ? tasks : filter === 'critical' ? critTasks : otherTasks;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(span * f));

  return (
    <div className="cs">
      <div className="cs-head">
        <div>
          <span className="chip ink">C03 // Timeline &amp; critical path</span>
          <h1>Timeline prediction &amp; critical path</h1>
          <div className="meta">
            {run.projectName || 'My House'}
            {timeline
              ? ` · ${num(totalWeeks)} weeks (${timeline.total_project_duration_days ?? '—'} days) · critical path ${Math.round(critRatio * 100)}% of programme`
              : ' · predict a programme from the costed quantities'}
          </div>
        </div>
        <div className="cs-head-side">
          <div className="btn-row" style={{ alignItems: 'flex-end' }}>
            <label className="field">
              <span className="eyebrow dim">Planned start</span>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
            <button onClick={runPrediction} disabled={predict.isPending || Boolean(scopeError)}>
              {predict.isPending ? 'Predicting…' : timeline ? 'Recalculate programme' : 'Generate timeline'}
            </button>
          </div>
          {timeline && (
            <div className="btn-row">
              <button className="sm" onClick={() => downloadSchedule(timeline, codes, isCrit)}>
                Export programme (CSV)
              </button>
              <button className="primary sm" onClick={() => nav('/step/4')} disabled={!run.step3?.schedulePayload}>
                Handoff to C04 monitoring →
              </button>
            </div>
          )}
        </div>
      </div>

      <section className="cs-panel">
        <div className="between" style={{ marginBottom: '1rem' }}>
          <span className="eyebrow">Construction scope</span>
          <span className="eyebrow dim">The timeline covers the floors you build now</span>
        </div>
        <div className="grid cols-4">
          <label className="field">
            Planned total floors
            <input
              type="number"
              min={1}
              value={plannedTotalFloors}
              readOnly
              title="Planned total floors comes from the design and cost steps."
            />
          </label>
          <label className="field">
            Floors to build now
            <input
              type="number"
              min={1}
              max={plannedTotalFloors}
              value={timelineRequiredFloors}
              onChange={(e) => setTimelineRequiredFloors(Number(e.target.value))}
            />
          </label>
          <label className="field">
            Scope
            <input
              value={scopeType === 'full_construction' ? 'Full construction' : 'Partial construction'}
              readOnly
              title="Worked out from the two floor counts."
            />
          </label>
          <label className="field">
            Scope description
            <input value={scopeDescription} onChange={(e) => setScopeDescription(e.target.value)} />
          </label>
        </div>
        {scopeError ? (
          <div className="alert warn" style={{ marginTop: '1rem' }}>
            {scopeError}
          </div>
        ) : (
          <p className="faint" style={{ margin: '0.75rem 0 0' }}>
            The cost estimate may cover the whole design; the programme is generated for the scope
            selected here.
            {scopeSummary.message ? ` ${String(scopeSummary.message)}.` : ''}
          </p>
        )}
      </section>

      {predict.isError && (
        <ErrorBox error={predict.error} onRetry={scopeError ? undefined : runPrediction} />
      )}
      {predict.isPending && (
        <section className="cs-panel">
          <div className="loading">
            <span className="spinner" aria-hidden /> Predicting phase durations…
          </div>
        </section>
      )}
      {noPayload && (
        <div className="alert warn">
          This programme came back without a monitoring baseline, so site monitoring cannot start
          from it. Try a different planned start date.
        </div>
      )}

      {timeline && (
        <>
          <div className="cs-layers">
            <div className="cs-layer">
              <div className="between">
                <span className="eyebrow dim">Layer 01 // Cost input</span>
                <span className="chip">Ingested</span>
              </div>
              <h3>C02 building specification</h3>
              <p>
                {num(estimateReport.feeds_downstream.floor_area_sqm, 0)} m² floor area,{' '}
                {estimateReport.feeds_downstream.total_labour_days.toLocaleString('en-LK')} labour-days,
                budget base Rs {(estimateReport.summary.total_lkr / 1e6).toFixed(2)}M.
              </p>
            </div>
            <div className="cs-layer">
              <div className="between">
                <span className="eyebrow dim">Layer 02 // Phase model</span>
                <span className="chip nominal">Active</span>
              </div>
              <h3>Phase duration predictors</h3>
              <p>
                XGBoost predicts each of {phases.length} phase durations, with a Random Forest kept as
                a fallback.
              </p>
              <span className="foot">
                <span className="dot" /> {mp?.xgboost_status ? titleCase(mp.xgboost_status) : 'Phase model used'}
              </span>
            </div>
            <div className="cs-layer hot">
              <div className="between">
                <span className="eyebrow">Layer 03 // Sequence model</span>
                <span className="chip critical">Cross-check</span>
              </div>
              <h3>PyTorch sequence LSTM</h3>
              <p>
                Reads the phase sequence and predicts the total independently
                {lstmWeeks != null ? `: ${num(lstmWeeks)} weeks.` : '.'}
              </p>
              <span className="foot">
                <span className="dot terra" /> {mp?.lstm_status ? titleCase(mp.lstm_status) : 'Sequence model'}
              </span>
            </div>
            <div className="cs-layer">
              <div className="between">
                <span className="eyebrow dim">Layer 04 // Network</span>
                <span className="chip ink">Solved</span>
              </div>
              <h3>Precedence network &amp; critical path</h3>
              <p>
                {tasks.length} activities ordered by their dependencies; {critTasks.length} sit on the
                critical path.
              </p>
            </div>
          </div>

          <div className="cs-main">
            <section className="cs-panel">
              <div className="between">
                <span className="eyebrow dim">Master schedule synthesiser</span>
                <span className="chip">Confidence {pct(timeline.confidence_score)}</span>
              </div>
              <div className="ts-hero">
                <div>
                  <span className="eyebrow dim">Predicted programme duration</span>
                  <div className="ts-big">
                    {num(totalWeeks)}
                    <span>weeks</span>
                  </div>
                  <p className="faint" style={{ margin: 0 }}>
                    {timeline.total_project_duration_days ?? '—'} calendar days ·{' '}
                    {dateStr(tasks[0]?.start_date)} → {dateStr(tasks[tasks.length - 1]?.end_date)}
                  </p>
                </div>
                {lstmWeeks != null && (
                  <div className="ts-compare">
                    <span className="eyebrow dim">Sequence model total</span>
                    <b>{num(lstmWeeks)} wks</b>
                    <span className={`chip ${lstmWeeks <= totalWeeks ? 'nominal' : 'review'}`}>
                      {lstmWeeks <= totalWeeks ? '−' : '+'}
                      {num(Math.abs(totalWeeks - lstmWeeks))} wks vs schedule
                    </span>
                    <p>The scheduled total adds sequencing and dependency waits to the model's estimate.</p>
                  </div>
                )}
              </div>

              <div className="between" style={{ margin: '1.25rem 0 0.5rem' }}>
                <span className="eyebrow dim">Phase allocation proportions</span>
                <span className="eyebrow dim">{num(phaseWeeksTotal)} phase-weeks</span>
              </div>
              <div className="ts-stack" role="img" aria-label="Share of programme by phase">
                {phases.map(([k, w], i) => (
                  <span
                    key={k}
                    style={{
                      flexGrow: w,
                      background: PHASE_TONES[i % PHASE_TONES.length],
                      // Ink flips to near-white in dark mode; its label has to flip with it.
                      color: PHASE_TONES[i % PHASE_TONES.length] === 'var(--ink)' ? 'var(--on-ink)' : '#fff',
                    }}
                    title={`${titleCase(k)}: ${num(w)} weeks`}
                  >
                    {w / phaseWeeksTotal > 0.07 ? `${num(w)}w` : ''}
                  </span>
                ))}
              </div>
              <div className="ts-legend">
                {phases.map(([k, w], i) => (
                  <span key={k}>
                    <i style={{ background: PHASE_TONES[i % PHASE_TONES.length] }} />
                    {titleCase(k)} ({num(w)}w)
                  </span>
                ))}
              </div>
            </section>

            <section className="cs-panel">
              <div className="between">
                <span className="eyebrow dim">CPM network diagnosis</span>
                <span className="chip critical">{critTasks.length} critical</span>
              </div>
              <div className="ts-counts">
                <div>
                  <span className="eyebrow dim">Critical activities</span>
                  <b className="terra">{critTasks.length} tasks</b>
                  <small>{num(critWeeks)} weeks in sequence</small>
                </div>
                <div>
                  <span className="eyebrow dim">Non-critical</span>
                  <b style={{ color: 'var(--accent)' }}>{otherTasks.length} tasks</b>
                  <small>Can run alongside the critical chain</small>
                </div>
              </div>
              <span className="eyebrow dim" style={{ display: 'block', margin: '1rem 0 0.5rem' }}>
                Milestones
              </span>
              {timeline.milestones.length === 0 ? (
                <p className="faint">No milestones returned.</p>
              ) : (
                <div className="ts-milestones">
                  {timeline.milestones.map((m, i) => {
                    const crit = isCrit(m.phase);
                    return (
                      <div key={i} className={crit ? 'crit' : ''}>
                        <div>
                          <b>
                            M{i + 1}: {m.name}
                          </b>
                          <small>{titleCase(m.phase)}</small>
                        </div>
                        <div className="r">
                          <b>Wk {m.week}</b>
                          <small>{crit ? 'Critical' : 'Non-critical'}</small>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              {peakCrew.length > 0 && (
                <div className="ts-crew">
                  <span className="eyebrow dim">Peak crew</span>
                  {peakCrew.slice(0, 4).map(([k, n]) => (
                    <span key={k} className="chip">
                      {titleCase(k)}: <b>{n}</b>
                    </span>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className="cs-boq">
            <header>
              <div>
                <span className="eyebrow dim">Critical path matrix</span>
                <h2>Phase schedule ({tasks.length} activities)</h2>
              </div>
              <div className="cs-filters" role="group" aria-label="Filter activities">
                <span className="eyebrow dim">Filter:</span>
                <button aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>
                  All ({tasks.length})
                </button>
                <button aria-pressed={filter === 'critical'} onClick={() => setFilter('critical')}>
                  Critical ({critTasks.length})
                </button>
                <button aria-pressed={filter === 'other'} onClick={() => setFilter('other')}>
                  Non-critical ({otherTasks.length})
                </button>
              </div>
            </header>
            <div className="table-wrap">
              <table className="ts-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Phase &amp; task</th>
                    <th>Pred.</th>
                    <th>Start</th>
                    <th>Finish</th>
                    <th className="num">Days</th>
                    <th className="ts-bar-col">Timeline (week 0 — {num(span, 0)})</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((t) => {
                    const crit = isCrit(t.task);
                    const pred = (deps.get(taskKey(t.task)) ?? []).map((d) => codes.get(taskKey(d)) ?? titleCase(d));
                    const left = ((t.start_week - 1) / span) * 100;
                    const width = Math.max((t.duration_weeks / span) * 100, 0.8);
                    return (
                      <tr key={t.id} className={crit ? 'crit' : ''}>
                        <td className="code">{codes.get(taskKey(t.task))}</td>
                        <td>
                          <b>{titleCase(t.task)}</b>
                          <div className="faint">{stageExplanation(t.task)}</div>
                        </td>
                        <td className="faint">{pred.length ? pred.join(', ') : '—'}</td>
                        <td>
                          Wk {num(t.start_week - 1)}
                          <div className="faint">{dateStr(t.start_date)}</div>
                        </td>
                        <td>
                          Wk {num(t.end_week - 1)}
                          <div className="faint">{dateStr(t.end_date)}</div>
                        </td>
                        <td className="num">{durationLabel(t).replace(' days', '')}</td>
                        <td className="ts-bar-col">
                          <div className="ts-track">
                            <span style={{ left: `${left}%`, width: `${width}%` }} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={6} />
                    <td className="ts-bar-col">
                      <div className="ts-ticks">
                        {ticks.map((w, i) => (
                          <span key={i} className={i === ticks.length - 1 ? 'terra' : ''}>
                            W{w}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <footer>
              <span>
                <span className="ts-key crit" /> Critical — a delay here moves the end date ·{' '}
                <span className="ts-key" /> Non-critical
              </span>
            </footer>
          </section>

          {crews.length > 0 && (
            <section className="cs-panel">
              <span className="eyebrow dim">Resource allocation</span>
              <div className="table-wrap" style={{ marginTop: '0.75rem' }}>
                <table className="st-table">
                  <thead>
                    <tr>
                      <th>Construction stage</th>
                      <th>Labour / crew</th>
                      <th className="num">Workers</th>
                      <th>Equipment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {crews.map((row) => (
                      <tr key={row.stage}>
                        <td>
                          <b>{titleCase(row.stage)}</b>
                        </td>
                        <td>{row.crew}</td>
                        <td className="num">{row.workers}</td>
                        <td className="faint">{titleCase(row.equipment)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <div className="cs-status">
            <div className="chips">
              <span className="chip">
                <span className="dot" /> Phase model: <b>{titleCase(mp?.phase_duration_model ?? 'xgboost').replace('Xgboost', 'XGBoost')}</b>
              </span>
              <span className="chip">
                Critical path: <b>{critTasks.length} of {tasks.length} activities</b>
              </span>
              <span className="chip">
                Confidence: <b className="terra">{pct(timeline.confidence_score)}</b>
              </span>
            </div>
            <div className="btn-row">
              <button className="ghost" onClick={() => nav('/step/2')}>
                ← Cost
              </button>
              <button disabled={predict.isPending || Boolean(scopeError)} onClick={runPrediction}>
                Recalculate programme
              </button>
              <button className="primary" onClick={() => nav('/step/4')} disabled={!run.step3?.schedulePayload}>
                Proceed to C04 site monitoring →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
