import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
// frappe-gantt does not ship TypeScript declarations in v1.2.2.
// @ts-expect-error missing package declaration
import FrappeGantt from 'frappe-gantt';
import '../../node_modules/frappe-gantt/dist/frappe-gantt.css';
import { post } from '../api/client';
import { Badge, Card, ErrorBox, Stat, dateStr, num, pct, titleCase } from '../components/ui';
import type { CostReport, RunState, TimelineResponse } from '../types';

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

interface FrappeTask {
  id: string;
  name: string;
  start: string;
  end: string;
  progress: number;
  dependencies: string;
  custom_class: string;
  duration_days: number | null;
  duration_weeks: number;
  task_type: 'Critical Path' | 'Normal Task';
  explanation: string;
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

function taskId(value: string): string {
  return taskKey(value).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'task';
}

function isCriticalTask(taskName: string, criticalPath: string[]): boolean {
  const name = taskKey(taskName);
  return criticalPath.some((critical) => {
    const key = taskKey(critical);
    return key === name || key.includes(name) || name.includes(key);
  });
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function toFrappeTasks(timeline: TimelineResponse): FrappeTask[] {
  const schedule = (timeline.gantt_chart_data ?? []).filter((task) => task.start_date && task.end_date);
  const idByTask = new Map(schedule.map((task) => [taskKey(task.task), taskId(task.task)]));
  const depsByTask = new Map(
    (timeline.task_dependencies ?? []).map((dep) => [
      taskKey(dep.task),
      dep.depends_on.map((name) => idByTask.get(taskKey(name))).filter(Boolean) as string[],
    ]),
  );

  return schedule.map((task) => {
    const isCritical = isCriticalTask(task.task, timeline.critical_path ?? []);
    const dependencies = depsByTask.get(taskKey(task.task)) ?? [];

    return {
      id: taskId(task.task),
      name: titleCase(task.task),
      start: task.start_date!,
      end: task.end_date!,
      progress: 0,
      dependencies: dependencies.join(', '),
      custom_class: isCritical ? 'timeline-frappe-critical' : 'timeline-frappe-normal',
      duration_days: task.duration_days,
      duration_weeks: task.duration_weeks,
      task_type: isCritical ? 'Critical Path' : 'Normal Task',
      explanation: stageExplanation(task.task),
    };
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

function ProjectGanttChart({ timeline }: { timeline: TimelineResponse }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [viewMode, setViewMode] = useState<'Day' | 'Week' | 'Month'>('Week');
  const [selectedTask, setSelectedTask] = useState<FrappeTask | null>(null);
  const tasks = useMemo(() => toFrappeTasks(timeline), [timeline]);

  useEffect(() => {
    if (!containerRef.current || tasks.length === 0) return undefined;

    containerRef.current.innerHTML = '';
    new FrappeGantt(containerRef.current, tasks, {
      view_mode: viewMode,
      popup_on: 'click',
      readonly: true,
      readonly_dates: true,
      readonly_progress: true,
      view_mode_select: false,
      date_format: 'YYYY-MM-DD',
      bar_height: 24,
      padding: 18,
      lines: 'both',
      scroll_to: 'start',
      popup: ({ task }: { task: FrappeTask }) => {
        const duration = task.duration_days
          ? `${task.duration_days} Days`
          : `${num(task.duration_weeks)} Weeks`;
        return `
          <div class="timeline-frappe-popup">
            <strong>${escapeHtml(task.name)}</strong>
            <dl>
              <dt>Start Date</dt><dd>${escapeHtml(dateStr(task.start))}</dd>
              <dt>End Date</dt><dd>${escapeHtml(dateStr(task.end))}</dd>
              <dt>Duration</dt><dd>${escapeHtml(duration)}</dd>
              <dt>Type</dt><dd>${escapeHtml(task.task_type)}</dd>
            </dl>
            <p>${escapeHtml(task.explanation)}</p>
          </div>
        `;
      },
      on_click: (task: FrappeTask) => setSelectedTask(task),
    });

    const focusTimer = window.setTimeout(() => {
      const wrapper = containerRef.current?.querySelector<HTMLElement>('.gantt-container');
      const firstBar =
        wrapper?.querySelector<Element>('.bar-wrapper') ??
        wrapper?.querySelector<Element>('.bar-wrapper .bar');

      if (!wrapper || !firstBar) return;

      const wrapperRect = wrapper.getBoundingClientRect();
      const barRect = firstBar.getBoundingClientRect();
      const delta = barRect.left - wrapperRect.left - 24;

      if (delta < 0 || barRect.left > wrapperRect.right) {
        wrapper.scrollLeft = Math.max(0, wrapper.scrollLeft + delta);
      }
    }, 80);

    return () => {
      window.clearTimeout(focusTimer);
      if (containerRef.current) containerRef.current.innerHTML = '';
    };
  }, [tasks, viewMode]);

  if (tasks.length === 0) return <p className="faint">No timeline schedule is available.</p>;

  return (
    <div className="stack">
      <div className="between">
        <div className="row">
          <Badge tone="danger">Red — Critical Path: delay may affect project completion</Badge>
          <Badge tone="neutral">Blue — Normal Task: non-critical scheduled work</Badge>
        </div>
        <div className="row">
          {(['Day', 'Week', 'Month'] as const).map((mode) => (
            <button
              key={mode}
              className={viewMode === mode ? 'primary' : 'ghost'}
              onClick={() => setViewMode(mode)}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      <div className="timeline-frappe-wrap">
        <div ref={containerRef} />
      </div>

      {selectedTask && (
        <div className="table-wrap">
          <table>
            <tbody>
              <tr>
                <th style={{ width: 180 }}>Selected Stage</th>
                <td>{selectedTask.name}</td>
              </tr>
              <tr>
                <th>Start Date</th>
                <td>{dateStr(selectedTask.start)}</td>
              </tr>
              <tr>
                <th>End Date</th>
                <td>{dateStr(selectedTask.end)}</td>
              </tr>
              <tr>
                <th>Duration</th>
                <td>
                  {selectedTask.duration_days
                    ? `${selectedTask.duration_days} Days`
                    : `${num(selectedTask.duration_weeks)} Weeks`}
                </td>
              </tr>
              <tr>
                <th>Task Type</th>
                <td>{selectedTask.task_type}</td>
              </tr>
              <tr>
                <th>Explanation</th>
                <td className="faint">{selectedTask.explanation}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <style>{`
        .timeline-frappe-wrap {
          --timeline-gantt-bg: #151c2c;
          --timeline-gantt-row: #121a2a;
          --timeline-gantt-row-alt: #172033;
          --timeline-gantt-border: #2a3953;
          --timeline-gantt-border-strong: #3a4a68;
          --timeline-gantt-text: var(--text);
          --timeline-gantt-muted: var(--muted);
          --g-arrow-color: #9aa8bd;
          --g-bar-color: var(--accent);
          --g-bar-border: transparent;
          --g-tick-color: var(--timeline-gantt-border);
          --g-tick-color-thick: var(--timeline-gantt-border-strong);
          --g-border-color: var(--timeline-gantt-border);
          --g-text-muted: var(--timeline-gantt-muted);
          --g-text-light: var(--timeline-gantt-text);
          --g-text-dark: var(--timeline-gantt-text);
          --g-progress-color: rgba(241, 245, 249, 0.22);
          --g-header-background: #182235;
          --g-row-color: var(--timeline-gantt-row);
          --g-row-border-color: var(--timeline-gantt-border);
          --g-today-highlight: #cbd5e1;
          --g-weekend-highlight-color: var(--timeline-gantt-row-alt);
          min-height: 360px;
          overflow-x: auto;
          overflow-y: hidden;
          border: 1px solid var(--border);
          border-radius: 14px;
          background: var(--timeline-gantt-bg);
        }
        .timeline-frappe-wrap .gantt-container {
          min-height: 360px;
          color: var(--timeline-gantt-text);
          background: var(--timeline-gantt-bg);
        }
        .timeline-frappe-wrap .gantt {
          background: var(--timeline-gantt-bg);
        }
        .timeline-frappe-wrap .gantt > g.bar {
          background: transparent;
          border-radius: 0;
          height: auto;
          overflow: visible;
        }
        .timeline-frappe-wrap .gantt .bar-wrapper rect.bar {
          background: transparent;
          border-radius: 0;
          height: 24px;
          overflow: visible;
        }
        .timeline-frappe-wrap .grid-header {
          background-color: var(--g-header-background);
          border-bottom-color: var(--timeline-gantt-border-strong);
        }
        .timeline-frappe-wrap .gantt .grid-background {
          fill: none;
        }
        .timeline-frappe-wrap .gantt .grid-row {
          fill: var(--timeline-gantt-row);
        }
        .timeline-frappe-wrap .gantt .row-line {
          stroke: var(--timeline-gantt-border);
        }
        .timeline-frappe-wrap .gantt .tick {
          stroke: var(--timeline-gantt-border);
        }
        .timeline-frappe-wrap .gantt .tick.thick {
          stroke: var(--timeline-gantt-border-strong);
        }
        .timeline-frappe-wrap .grid-header,
        .timeline-frappe-wrap .grid-row,
        .timeline-frappe-wrap .lower-text,
        .timeline-frappe-wrap .upper-text {
          fill: var(--timeline-gantt-muted);
          color: var(--timeline-gantt-muted);
        }
        .timeline-frappe-wrap .upper-text,
        .timeline-frappe-wrap .current-upper {
          color: var(--timeline-gantt-text);
          fill: var(--timeline-gantt-text);
        }
        .timeline-frappe-wrap .current-upper {
          background: var(--g-header-background);
        }
        .timeline-frappe-wrap .gantt .bar-label {
          fill: #f8fafc;
          font-weight: 700;
          paint-order: stroke;
          stroke: rgba(15, 23, 42, 0.45);
          stroke-width: 2px;
        }
        .timeline-frappe-wrap .gantt .bar-label.big {
          fill: var(--timeline-gantt-text);
          stroke: none;
        }
        .timeline-frappe-wrap .timeline-frappe-critical .bar {
          fill: var(--danger);
          stroke: rgba(248, 113, 113, 0.35);
        }
        .timeline-frappe-wrap .timeline-frappe-critical .bar-progress {
          fill: var(--danger);
        }
        .timeline-frappe-wrap .timeline-frappe-normal .bar {
          fill: var(--accent);
          stroke: rgba(96, 165, 250, 0.35);
        }
        .timeline-frappe-wrap .timeline-frappe-normal .bar-progress {
          fill: var(--accent);
        }
        .timeline-frappe-wrap .gantt .arrow {
          stroke: var(--g-arrow-color);
        }
        .timeline-frappe-wrap .current-highlight,
        .timeline-frappe-wrap .current-ball-highlight,
        .timeline-frappe-wrap .current-date-highlight {
          background: var(--g-today-highlight);
        }
        .timeline-frappe-wrap .current-date-highlight {
          color: #0f172a;
        }
        .timeline-frappe-wrap .today-button {
          background: var(--surface);
          border: 1px solid var(--border);
          color: var(--text);
        }
        .timeline-frappe-wrap .today-button:hover {
          background: var(--accent);
          border-color: var(--accent);
          color: #ffffff;
        }
        .timeline-frappe-wrap .popup-wrapper {
          color: #0f172a;
        }
        .timeline-frappe-popup {
          max-width: 280px;
          color: #0f172a;
          line-height: 1.45;
        }
        .timeline-frappe-popup strong {
          display: block;
          margin-bottom: 8px;
          color: #0f172a;
          font-size: 14px;
        }
        .timeline-frappe-popup dl {
          display: grid;
          grid-template-columns: 88px 1fr;
          gap: 4px 10px;
          margin: 0 0 8px;
        }
        .timeline-frappe-popup dt {
          color: #475569;
          font-weight: 700;
        }
        .timeline-frappe-popup dd {
          margin: 0;
          color: #0f172a;
        }
        .timeline-frappe-popup p {
          margin: 8px 0 0;
          color: #334155;
        }
      `}</style>
    </div>
  );
}

function ResourceAllocation({ timeline }: { timeline: TimelineResponse }) {
  const rows = resourceRows(timeline.resource_allocation_plan);

  if (rows.length === 0) {
    return <p className="faint">No resource allocation data returned by the Timeline API.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Construction Stage</th>
            <th>Labour / Crew</th>
            <th className="num">Workers</th>
            <th>Equipment / Resources</th>
            <th>Duration / Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.stage}>
              <td>{titleCase(row.stage)}</td>
              <td>{row.crew}</td>
              <td className="num">{row.workers}</td>
              <td className="faint">{row.equipment}</td>
              <td className="faint">{row.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CustomerTimeline({ timeline }: { timeline: TimelineResponse }) {
  const tasks = timeline.gantt_chart_data ?? [];

  if (tasks.length === 0) return <p className="faint">No customer timeline data returned.</p>;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th className="num">No.</th>
            <th>Construction Stage</th>
            <th>Start Date</th>
            <th>End Date</th>
            <th>Duration</th>
            <th>Explanation</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task, index) => (
            <tr key={task.id}>
              <td className="num">{index + 1}</td>
              <td>{titleCase(task.task)}</td>
              <td>{dateStr(task.start_date)}</td>
              <td>{dateStr(task.end_date)}</td>
              <td>{durationLabel(task)}</td>
              <td className="faint">{stageExplanation(task.task)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
  const scopeSummary = asRecord(timeline?.input_summary?.construction_scope_summary) as
    | Record<string, unknown>
    | undefined;

  return (
    <div className="stack">
      <div className="between">
        <div>
          <h1>Timeline</h1>
          <p className="muted">
            Phase durations predicted from the cost estimate's labour and complexity signals.
          </p>
        </div>
        <div className="row">
          <label className="field">
            Planned start
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <button onClick={runPrediction} disabled={predict.isPending || Boolean(scopeError)}>
            {predict.isPending ? 'Predicting…' : timeline ? 'Re-predict' : 'Generate Timeline'}
          </button>
        </div>
      </div>

      <Card
        title="Customer Construction Scope"
        subtitle="Timeline prediction is generated for the customer-selected construction stage."
      >
        <div className="grid cols-4">
          <label className="field">
            Planned Total Floors
            <input
              type="number"
              min={1}
              value={plannedTotalFloors}
              readOnly
              title="Planned total floors comes from the previous Design / Materials & Cost step."
            />
          </label>
          <label className="field">
            Timeline Required Floors
            <input
              type="number"
              min={1}
              max={plannedTotalFloors}
              value={timelineRequiredFloors}
              onChange={(e) => setTimelineRequiredFloors(Number(e.target.value))}
            />
          </label>
          <label className="field">
            Scope Type
            <input value={scopeType} readOnly title="Scope type is calculated automatically." />
          </label>
          <label className="field">
            Scope Description
            <input
              value={scopeDescription}
              onChange={(e) => setScopeDescription(e.target.value)}
            />
          </label>
        </div>
        {scopeError ? (
          <div className="alert warn">{scopeError}</div>
        ) : (
          <p className="faint">
            Cost estimation may be based on the full building design, but the timeline is generated
            based on the customer-selected construction scope.
          </p>
        )}
        {scopeSummary && Object.keys(scopeSummary).length > 0 && (
          <>
            <hr className="divider" />
            <div className="grid cols-4">
              <Stat
                label="Planned total floors"
                value={String(scopeSummary.planned_total_floors ?? plannedTotalFloors)}
              />
              <Stat
                label="Timeline required floors"
                value={String(scopeSummary.timeline_required_floors ?? timelineRequiredFloors)}
              />
              <Stat label="Scope type" value={String(scopeSummary.scope_type ?? scopeType)} />
              <Stat label="Message" value={String(scopeSummary.message ?? 'Scope applied')} />
            </div>
            <p className="faint">
              {String(scopeSummary.scope_description ?? constructionScope.scope_description)}
            </p>
          </>
        )}
      </Card>

      {predict.isError && (
        <ErrorBox error={predict.error} onRetry={scopeError ? undefined : runPrediction} />
      )}
      {predict.isPending && !timeline && (
        <Card>
          <div className="loading">
            <span className="spinner" aria-hidden /> Predicting phase durations…
          </div>
        </Card>
      )}
      {noPayload && (
        <div className="alert warn">
          Timeline returned no <span className="mono">performance_monitoring_payload</span>, so
          step 4 cannot be seeded. Try a different planned start date.
        </div>
      )}

      {timeline && (
        <>
          <div className="grid cols-4">
            <Stat
              label="Total duration"
              value={`${num(timeline.total_project_duration_weeks)} wk`}
              hint={
                timeline.total_project_duration_days
                  ? `${timeline.total_project_duration_days} days`
                  : undefined
              }
            />
            <Stat label="Phases" value={phases.length} />
            <Stat label="Critical path" value={timeline.critical_path.length} hint="tasks" />
            <Stat label="Confidence" value={pct(timeline.confidence_score)} />
          </div>

          <Card
            title="Construction Timeline for Customer"
            subtitle="Simple stage-by-stage view using the predicted schedule dates."
          >
            <CustomerTimeline timeline={timeline} />
          </Card>

          <Card title="Project Gantt Chart" subtitle="Technical project-management schedule">
            <ProjectGanttChart timeline={timeline} />
          </Card>

          <div className="grid cols-2">
            <Card title="Phase durations">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Phase</th>
                      <th className="num">Weeks</th>
                      <th className="num">Days</th>
                    </tr>
                  </thead>
                  <tbody>
                    {phases.map(([k, v]) => (
                      <tr key={k}>
                        <td>{titleCase(k)}</td>
                        <td className="num">{num(v)}</td>
                        <td className="num">
                          {timeline.predicted_phase_durations_days?.[k] ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Milestones">
              {timeline.milestones.length === 0 ? (
                <p className="faint">No milestones returned.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Milestone</th>
                        <th>Phase</th>
                        <th className="num">Week</th>
                      </tr>
                    </thead>
                    <tbody>
                      {timeline.milestones.map((m, i) => (
                        <tr key={i}>
                          <td>{m.name}</td>
                          <td className="faint">{titleCase(m.phase)}</td>
                          <td className="num">{m.week}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <hr className="divider" />
            </Card>
          </div>

          <Card
            title="Resource Allocation"
            subtitle="Crew and equipment plan returned by the Timeline API."
          >
            <ResourceAllocation timeline={timeline} />
          </Card>

          <Card title="Critical Path">
            <div className="row">
              <span className="faint">Critical path:</span>
              {timeline.critical_path.map((c) => (
                <Badge key={c} tone="danger">
                  {titleCase(c)}
                </Badge>
              ))}
            </div>
          </Card>
        </>
      )}

      {timeline && (
        <div className="footer-nav">
          <button onClick={() => nav('/step/2')}>← Cost</button>
          <button
            className="primary"
            onClick={() => nav('/step/4')}
            disabled={!run.step3?.schedulePayload}
          >
            Move to Performance →
          </button>
        </div>
      )}
    </div>
  );
}
