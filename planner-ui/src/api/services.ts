import { get, post } from './client';
import type {
  BuildingSchema,
  CostReport,
  Dashboard,
  MaterialCatalog,
  PredictResponse,
  ScheduleCreated,
  SchedulePayload,
  SpiResponse,
  TimelineResponse,
} from '../types';

/* ───────────────────────────── C02 — Cost Estimation ───────────────────────── */

export const fetchMaterials = () => get<MaterialCatalog>('c02', '/materials');

export const estimate = (schema: BuildingSchema, materials: Record<string, string>) =>
  post<CostReport>('c02', '/estimate', { ...schema, materials });

/* ─────────────────────────────── C03 — Timeline ────────────────────────────── */

export interface TimelineRequestExtras {
  projectId: string;
  projectName: string;
  plannedStartDate: string;
  location: string;
  buildingType?: string;
}

/** C03's /predict takes a loose dict — this minimal body is verified to work.
 *  The estimate's rate_metadata and feeds_downstream pass through untouched. */
function timelineBody(estimateReport: CostReport, x: TimelineRequestExtras) {
  return {
    project_id: x.projectId,
    project_name: x.projectName,
    planned_start_date: x.plannedStartDate,
    location: x.location,
    building_type: x.buildingType ?? 'residential',
    rate_metadata: estimateReport.rate_metadata,
    feeds_downstream: estimateReport.feeds_downstream,
    total_estimated_cost: estimateReport.summary.total_lkr,
  };
}

export const predictTimeline = (r: CostReport, x: TimelineRequestExtras) =>
  post<TimelineResponse>('c03', '/api/timeline/predict', timelineBody(r, x));

/** Returns only the C04-shaped schedule payload. */
export const timelineSchedulePayload = (r: CostReport, x: TimelineRequestExtras) =>
  post<SchedulePayload>('c03', '/api/timeline/performance-format', timelineBody(r, x));

/* ───────────────────────────── C04 — Performance ───────────────────────────── */

/** Post C03's payload completely unmodified. C04 returns its OWN integer
 *  project_id, unrelated to the id sent to C03 — capture and store it. */
export const seedSchedule = (payload: SchedulePayload) =>
  post<ScheduleCreated>('c04', '/schedule', payload);

export const submitSpi = (phaseId: number, actualPercent: number, enteredBy?: string) =>
  post<SpiResponse>('c04', '/progress/spi', {
    phase_id: phaseId,
    actual_percent: actualPercent,
    ...(enteredBy ? { entered_by: enteredBy } : {}),
  });

export interface PredictInput {
  spiId: number;
  phaseId: number;
  delayCategory: string;
  labourAvailability: string;
  materialSupply: string;
  /** Optional manual override — C04 fetches weather server-side otherwise. */
  weatherSeverity?: string;
}

export const predictDelay = (i: PredictInput) =>
  post<PredictResponse>('c04', '/progress/predict', {
    spi_id: i.spiId,
    phase_id: i.phaseId,
    delay_category: i.delayCategory,
    labour_availability: i.labourAvailability,
    material_supply: i.materialSupply,
    ...(i.weatherSeverity ? { weather_severity: i.weatherSeverity } : {}),
  });

export const fetchDashboard = (projectId: number) =>
  get<Dashboard>('c04', `/project/${projectId}/dashboard`);
