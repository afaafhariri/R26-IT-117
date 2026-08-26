import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { predictTimeline } from '../api/services';
import { Badge, Card, ErrorBox, Stat, dateStr, num, pct, titleCase } from '../components/ui';
import type { RunState, TimelineResponse } from '../types';

type Props = { run: RunState; update: (p: Partial<RunState>) => void };

/** Lightweight CSS Gantt — clearer than a charting library for date bars. */
function Gantt({ timeline }: { timeline: TimelineResponse }) {
  const tasks = timeline.gantt_chart_data ?? [];
  const max = Math.max(...tasks.map((t) => t.end_week), 1);
  const critical = new Set(timeline.critical_path.map((c) => c.toLowerCase()));

  if (tasks.length === 0) return <p className="faint">No Gantt data returned.</p>;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th style={{ width: 150 }}>Task</th>
            <th style={{ minWidth: 260 }}>Schedule</th>
            <th className="num">Weeks</th>
            <th>Dates</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => {
            const isCritical = critical.has(t.task.toLowerCase());
            const left = (t.start_week / max) * 100;
            const width = Math.max(((t.end_week - t.start_week) / max) * 100, 1.5);
            return (
              <tr key={t.id}>
                <td>
                  {t.task} {isCritical && <Badge tone="danger">critical</Badge>}
                </td>
                <td>
                  <div style={{ position: 'relative', height: 18 }}>
                    <div
                      style={{
                        position: 'absolute',
                        left: `${left}%`,
                        width: `${width}%`,
                        top: 4,
                        height: 10,
                        borderRadius: 5,
                        background: isCritical ? 'var(--danger)' : 'var(--accent)',
                        opacity: isCritical ? 0.85 : 0.7,
                      }}
                      title={`week ${num(t.start_week)} → ${num(t.end_week)}`}
                    />
                  </div>
                </td>
                <td className="num">{num(t.duration_weeks)}</td>
                <td className="faint">
                  {dateStr(t.start_date)} → {dateStr(t.end_date)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Step3Timeline({ run, update }: Props) {
  const nav = useNavigate();
  const estimateReport = run.step2?.estimate;

  const [startDate, setStartDate] = useState(
    run.step3?.schedulePayload?.planned_start_date ?? new Date().toISOString().slice(0, 10),
  );
  const [timeline, setTimeline] = useState<TimelineResponse | undefined>(run.step3?.timeline);

  const predict = useMutation({
    mutationFn: (start: string) =>
      predictTimeline(estimateReport!, {
        projectId: run.runId,
        projectName: run.projectName,
        plannedStartDate: start,
        location: estimateReport!.rate_metadata.district || 'Colombo',
      }),
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

  const ran = useRef(false);
  useEffect(() => {
    if (!estimateReport || ran.current) return;
    ran.current = true;
    if (!timeline) predict.mutate(startDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estimateReport]);

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
          <button onClick={() => predict.mutate(startDate)} disabled={predict.isPending}>
            {predict.isPending ? 'Predicting…' : 'Re-predict'}
          </button>
        </div>
      </div>

      {predict.isError && (
        <ErrorBox error={predict.error} onRetry={() => predict.mutate(startDate)} />
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

          <Card title="Schedule" subtitle="Critical-path tasks in red">
            <Gantt timeline={timeline} />
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
              <div className="row">
                <span className="faint">Critical path:</span>
                {timeline.critical_path.map((c) => (
                  <Badge key={c} tone="danger">
                    {titleCase(c)}
                  </Badge>
                ))}
              </div>
            </Card>
          </div>
        </>
      )}

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
    </div>
  );
}
