import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { post } from '../api/client';
import { ErrorBox, dateStr, num, titleCase } from '../components/ui';
import { adaptC03Response, buildC03Request } from '../api/timelineAdapter';
import type { C03DisplayTimeline, TimelinePredictionInputs } from '../api/timelineAdapter';
import type { CostReport, RunState, TimelineResponse } from '../types';
import { TimelineGantt } from './TimelineGantt';
import './Step3Timeline.css';

/* Step 3 displays the 11-activity schedule returned by the C03 project
 * management API; the same response carries C04's planned schedule payload. */

type Props = { run: RunState; update: (p: Partial<RunState>) => void };
type ScopeType = 'full_construction' | 'partial_construction';

interface PredictionArgs {
  inputs: TimelinePredictionInputs;
}

const DEFAULT_SCOPE_DESCRIPTION = 'Customer wants to construct only ground floor at this stage';
const FULL_SCOPE_DESCRIPTION = 'Customer wants to construct all planned floors at this stage';

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
  if (!Number.isInteger(timelineRequiredFloors)) return 'Timeline required floors must be a whole number.';
  if (plannedTotalFloors < 1) return 'Planned total floors must be at least 1.';
  if (timelineRequiredFloors < 1) return 'Timeline required floors must be at least 1.';
  if (timelineRequiredFloors > plannedTotalFloors) {
    return 'Timeline required floors cannot exceed planned total floors.';
  }
  return null;
}

function predictTimelineWithScope(run: RunState, inputs: TimelinePredictionInputs) {
  if (!run.step1?.buildingSchema || !run.step2?.estimate) {
    throw new Error('Complete the building design and cost estimate first.');
  }
  const body = buildC03Request(run.step1.buildingSchema, run.step2.estimate, inputs, run.runId, run.projectName);
  return post<C03DisplayTimeline>('c03', '/api/timeline/predict', body).then((response) =>
    adaptC03Response(response),
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
    return key === name;
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
    new Date().toISOString().slice(0, 10),
  );
  const [timeline, setTimeline] = useState<C03DisplayTimeline | undefined>();
  const plannedTotalFloors = initialFloors;
  const [timelineRequiredFloors, setTimelineRequiredFloors] = useState(
    Math.min(initialFloors, 1),
  );
  const [scopeDescription, setScopeDescription] = useState(DEFAULT_SCOPE_DESCRIPTION);
  const [filter, setFilter] = useState<Filter>('all');
  const resultsRef = useRef<HTMLDivElement>(null);


  const scopeType = scopeTypeFor(plannedTotalFloors, timelineRequiredFloors);
  const scopeError = scopeValidation(plannedTotalFloors, timelineRequiredFloors);
  const inputsValid = Boolean(run.step1?.buildingSchema);
  const predict = useMutation({
    mutationFn: ({ inputs }: PredictionArgs) => predictTimelineWithScope(run, inputs),
    onMutate: () => { setTimeline(undefined); update({ step3: undefined, step4: undefined }); },
    onSuccess: (result) => {
      setTimeline(result);
      if (result.performance_monitoring_payload) {
        update({ step3: { timeline: result, schedulePayload: result.performance_monitoring_payload } });
      }
    },
  });

  useEffect(() => {
    if (timeline) resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [timeline]);

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

  const runPrediction = () => {
    if (scopeError || !inputsValid) return;
    predict.mutate({
      inputs: {
        floorsToBuild: timelineRequiredFloors,
        scopeDescription,
        startDate,
      },
    });
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
  const maxPhaseDays = Math.max(1, ...phases.map(([phase]) => Number(timeline?.predicted_phase_durations_days?.[phase]) || 0));
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
            <button onClick={runPrediction} disabled={predict.isPending || Boolean(scopeError) || !inputsValid}>
              {predict.isPending ? 'Predicting…' : timeline ? 'Recalculate programme' : 'Generate Timeline'}
            </button>
          </div>
          {timeline && (
            <div className="btn-row">
              <button className="sm" onClick={() => downloadSchedule(timeline, codes, isCrit)}>
                Export programme (CSV)
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
              onChange={(e) => {
                const requiredFloors = Number(e.target.value);
                setTimelineRequiredFloors(requiredFloors);
                setScopeDescription((current) => {
                  if (requiredFloors === plannedTotalFloors && current === DEFAULT_SCOPE_DESCRIPTION) {
                    return FULL_SCOPE_DESCRIPTION;
                  }
                  if (requiredFloors < plannedTotalFloors && current === FULL_SCOPE_DESCRIPTION) {
                    return DEFAULT_SCOPE_DESCRIPTION;
                  }
                  return current;
                });
              }}
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
            Building details and cost are received from Design and Materials &amp; Cost. The selected floor count is sent to C03 with the costed BOQ.
            {scopeSummary.message ? ` ${String(scopeSummary.message)}.` : ''}
          </p>
        )}
        {scopeType === 'partial_construction' && <p className="faint">Partial-scope scenario: C03 receives the full-design BOQ and selected floor count. Its scope adjustment is an estimate; C02 has not supplied a separate partial-floor cost.</p>}
        {!run.step1?.buildingSchema && <div className="alert warn">Building design data is missing. Return to Step 1.</div>}
      </section>

      {predict.isError && (
        <ErrorBox error={predict.error} onRetry={scopeError || !inputsValid ? undefined : runPrediction} />
      )}
      {predict.isPending && (
        <section className="cs-panel">
          <div className="loading">
            <span className="spinner" aria-hidden /> Predicting phase durations…
          </div>
        </section>
      )}
      {timeline && (
        <>
          <div ref={resultsRef} />
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
                The trained phase model predicts {phases.length} phase durations. The backend calculates the critical path.
              </p>
              <span className="foot">
                <span className="dot" /> {mp?.xgboost_status ? titleCase(mp.xgboost_status) : 'Phase prediction complete'}
              </span>
            </div>
            <div className="cs-layer hot">
              <div className="between">
                <span className="eyebrow">Layer 03 // Sequence model</span>
                <span className="chip critical">Cross-check</span>
              </div>
              <h3>Sequence LSTM</h3>
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
                <span className="chip">C03 model prediction</span>
              </div>
              <div className="ts-hero">
                <div>
                  <span className="eyebrow dim">Predicted programme duration</span>
                  <div className="ts-big">
                    {num(totalWeeks)}
                    <span>weeks</span>
                  </div>
                  <p className="faint" style={{ margin: 0 }}>
                    {timeline.total_project_duration_days ?? '—'} days ·{' '}
                    {dateStr(timeline.performance_monitoring_payload?.planned_start_date)} → {dateStr(timeline.performance_monitoring_payload?.planned_end_date)}
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
                    <p>This is an independent model estimate; differences do not indicate a scheduling error.</p>
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

          <section className="cs-panel c03-summary-panel">
            <div className="between">
              <span className="eyebrow dim">Programme overview</span>
              <span className="chip">C03 model prediction</span>
            </div>
            <h2>Prediction Summary</h2>
            <div className="c03-summary-metrics">
              <div className="c03-summary-metric">
                <span className="eyebrow dim">Total duration</span>
                <strong>{num(totalWeeks)} weeks</strong>
                <p>{timeline.total_project_duration_days} days</p>
              </div>
              <div className="c03-summary-metric">
                <span className="eyebrow dim">Construction phases</span>
                <strong>{phases.length}</strong>
                <p>Predicted activities</p>
              </div>
              <div className="c03-summary-metric critical">
                <span className="eyebrow dim">Critical path tasks</span>
                <strong>{critTasks.length}</strong>
                <p>Of {tasks.length} scheduled activities</p>
              </div>
              {Number.isFinite(timeline.confidence_score) && timeline.confidence_score !== 0.88 && (
                <div className="c03-summary-metric">
                  <span className="eyebrow dim">Confidence</span>
                  <strong>{num(timeline.confidence_score * 100)}%</strong>
                </div>
              )}
            </div>
          </section>
          <section className="cs-boq c03-result-section">
            <header>
              <div>
                <span className="eyebrow dim">Planned stage dates</span>
                <h2>Construction Timeline for Customer</h2>
              </div>
              <span className="chip">{tasks.length} activities</span>
            </header>
            <div className="table-wrap"><table className="ts-table c03-stage-table">
              <thead><tr><th>Stage</th><th>Start date</th><th>End date</th><th>Duration</th><th>Explanation</th></tr></thead>
              <tbody>{tasks.map(task => <tr key={task.id} className={isCrit(task.task) ? 'crit' : ''}>
                <td><div className="c03-stage-label"><span>{String(task.id).padStart(2, '0')}</span><b>{titleCase(task.task)}</b></div></td>
                <td>{dateStr(task.start_date)}</td>
                <td>{dateStr(task.end_date)}</td>
                <td className="num">{durationLabel(task)}</td>
                <td className="faint">{stageExplanation(task.task)}</td>
              </tr>)}</tbody>
            </table></div>
            <footer className="c03-table-key"><span><i className="c03-key-critical" /> Critical path</span><span><i className="c03-key-normal" /> Other scheduled work</span></footer>
          </section>
          <TimelineGantt timeline={timeline} />
          <section className="cs-boq c03-result-section">
            <header>
              <div>
                <span className="eyebrow dim">Phase model output</span>
                <h2>Phase Durations</h2>
              </div>
              <span className="chip">{phases.length} activities</span>
            </header>
            <div className="table-wrap"><table className="ts-table c03-duration-table"><thead><tr><th>Construction phase</th><th className="num">Predicted weeks</th><th className="num">Days</th><th>Relative duration</th></tr></thead>
              <tbody>{phases.map(([phase, weeks], index) => <tr key={phase} className={isCrit(phase) ? 'crit' : ''}>
                <td><div className="c03-stage-label"><span>{String(index + 1).padStart(2, '0')}</span><b>{titleCase(phase)}</b></div></td>
                <td className="num">{num(weeks)}</td>
                <td className="num">{timeline.predicted_phase_durations_days?.[phase] ?? 'Unavailable'}</td>
                <td className="c03-duration-visual"><div className="c03-duration-track" aria-hidden="true"><span style={{ width: `${Math.max(0, (Number(timeline.predicted_phase_durations_days?.[phase]) || 0) / maxPhaseDays * 100)}%` }} /></div></td>
              </tr>)}</tbody>
            </table></div>
          </section>

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

          {(
            <section className="cs-panel">
              <span className="eyebrow dim">Resource allocation</span>
              <p className="faint">Crew plan returned by C03. Where C02 does not supply trade counts, C03 uses its prototype worker and equipment defaults.</p>
              <div className="table-wrap" style={{ marginTop: '0.75rem' }}>
                <table className="st-table">
                  <thead>
                    <tr>
                      <th>Construction stage</th>
                      <th>Labour / crew</th>
                      <th className="num">Workers</th>
                      <th>Equipment</th>
                      <th>Notes</th>
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
                        <td>{row.notes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="cs-panel"><h2>Critical Path</h2><div className="chips">{criticalPath.map(phase => <span className="chip critical" key={phase}>{phase}</span>)}</div></section>
          {!timeline.performance_monitoring_payload && <p className="faint">C04 handoff unavailable: the current C03 /predict endpoint does not return a performance monitoring payload. A compatible backend payload is required before continuing.</p>}

          <div className="cs-status">
            <div className="chips">
              <span className="chip">
                <span className="dot" /> Phase model: <b>{titleCase(mp?.phase_duration_model ?? 'xgboost').replace('Xgboost', 'XGBoost')}</b>
              </span>
              <span className="chip">
                Critical path: <b>{critTasks.length} of {tasks.length} activities</b>
              </span>

            </div>
            <div className="btn-row">
              <button className="ghost" onClick={() => nav('/step/2')}>
                ← Cost
              </button>
              <button disabled={predict.isPending || Boolean(scopeError) || !inputsValid} onClick={runPrediction}>
                Recalculate programme
              </button>
              <button disabled={!timeline.performance_monitoring_payload || predict.isPending} onClick={() => nav('/step/4')}>Move to Performance</button>

            </div>
          </div>
        </>
      )}
    </div>
  );
}
