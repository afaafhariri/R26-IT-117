import { useEffect, useRef, useState } from 'react';
// Frappe 1.2.2 ships JavaScript without TypeScript declarations.
// @ts-expect-error No declaration file supplied by frappe-gantt.
import Gantt from 'frappe-gantt';
import ganttCss from '../../node_modules/frappe-gantt/dist/frappe-gantt.css?raw';
import type { TimelineResponse } from '../types';
import { dateStr } from '../components/ui';

const escape = (value: string) => value.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!);
const key = (value: string) => value.toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();

/** Vendor styles are scoped to C03; they cannot restyle other components. */
export function TimelineGantt({ timeline }: { timeline: TimelineResponse }) {
  const host = useRef<HTMLDivElement>(null);
  const [view, setView] = useState('Week');
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string>();
  useEffect(() => {
    const container = host.current;
    if (!container) return;
    container.replaceChildren();
    setError('');
    const tasks = timeline.gantt_chart_data;
    const ids = new Map(tasks.map((task, i) => [key(task.task), `stage-${i}`]));
    const dependencies = new Map(timeline.task_dependencies.map(task => [key(task.task), task.depends_on]));
    try {
      const chart = new Gantt(container, tasks.map((task, i) => ({
        id: `stage-${i}`, name: task.task, start: task.start_date, end: task.end_date,
        dependencies: (dependencies.get(key(task.task)) ?? []).map(name => ids.get(key(name))).filter(Boolean),
        custom_class: timeline.critical_path.some(name => key(name) === key(task.task)) ? 'c03-critical' : 'c03-normal',
      })), {
        view_mode: view, view_modes: ['Day', 'Week', 'Month'], readonly: true,
        infinite_padding: false, scroll_to: 'start', container_height: 480,
        popup_on: 'click',
        popup: (ctx: { task: { id: string }; set_title: (s: string) => void; set_details: (s: string) => void; set_subtitle: (s: string) => void }) => {
          const task = tasks[Number(ctx.task.id.replace('stage-', ''))];
          setSelected(task.task);
          ctx.set_title(escape(task.task));
          ctx.set_subtitle('Planned schedule');
          ctx.set_details(`${escape(dateStr(task.start_date))} - ${escape(dateStr(task.end_date))}<br/>${task.duration_days} days`);
        },
      });
      // v1.2.2 selects the first view_modes entry during setup_options.
      chart.change_view_mode(view);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Chart could not be displayed.');
    }
    return () => container.replaceChildren();
  }, [timeline, view]);
  return <section className="cs-panel c03-gantt" style={{ minWidth: 0, maxWidth: '100%' }}>
    <style>{`@scope (.c03-gantt) { ${ganttCss} }
      .c03-gantt { --g-row-color: var(--surface); --g-header-background: var(--surface-hi); --g-border-color: var(--border); --g-row-border-color: var(--border); --g-tick-color: var(--border); --g-tick-color-thick: var(--border-strong); --g-text-dark: var(--text); --g-text-muted: var(--text-dim); --g-arrow-color: var(--text-dim); --g-actions-background: var(--surface-2); --g-today-highlight: var(--terra); --g-weekend-highlight-color: var(--surface-2); }
      .c03-gantt .c03-critical { --g-bar-color: #c25943; --g-bar-border: #c25943; }
      .c03-gantt .c03-normal { --g-bar-color: #4a6b82; --g-bar-border: #4a6b82; }
      .c03-gantt .gantt .bar-label { fill: white; font-family: var(--body); }
      .c03-gantt .gantt .bar-label.big { fill: var(--text); }
      /* Isolate Frappe rects from the team's generic 6px progress .bar rule. */
      .c03-gantt .gantt rect.bar { height: 30px; }
    `}</style>
    <div className="between"><h2>Interactive Gantt Chart</h2><div className="cs-filters" role="group" aria-label="Gantt view">
      {['Day', 'Week', 'Month'].map(mode => <button key={mode} aria-pressed={view === mode} onClick={() => setView(mode)}>{mode}</button>)}
    </div></div>
    <p className="faint"><span style={{ color: '#c25943' }}>Red: Critical path</span> · <span style={{ color: '#4a6b82' }}>Blue: Normal task</span></p>
    {error && <p className="alert warn">{error}</p>}
    <div ref={host} style={{ overflowX: 'auto', minWidth: 0 }} />
    {selected && <p className="faint">Selected stage: {selected}</p>}
  </section>;
}
