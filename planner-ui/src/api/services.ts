import { get, post, request } from './client';
import type {
  BuildingSchema,
  C01BuildableZone,
  C01CadastralData,
  C01FloorPlanAlternative,
  C01FullDesignPackage,
  C01UserRequirements,
  CostReport,
  Dashboard,
  MaterialCatalog,
  PredictResponse,
  ScheduleCreated,
  SchedulePayload,
  SpiResponse,
  TimelineResponse,
} from '../types';

/* ───────────────────────── Step 1 — Architecture (C01) ──────────────────────── */

export interface UploadCadastralResponse {
  job_id: string;
  cadastral_data: C01CadastralData;
  buildable_zone: C01BuildableZone;
  suggested_requirements?: Record<string, unknown>;
}

/** Multipart upload — bypasses post()'s JSON.stringify, same as client.ts's
 *  own FormData handling (it already skips setting Content-Type for it). */
export const uploadCadastral = (file: File) => {
  const form = new FormData();
  form.append('file', file);
  return request<UploadCadastralResponse>('c01', '/api/process-cadastral', {
    method: 'POST',
    body: form,
  });
};

export const triggerFloorPlanGeneration = (jobId: string, requirements: C01UserRequirements) =>
  post<{ job_id: string; status: string }>('c01', '/api/generate-floorplans', {
    job_id: jobId,
    user_requirements: requirements,
  });

export const pollFloorPlanStatus = (jobId: string) =>
  get<{ status: string; alternatives: C01FloorPlanAlternative[] | null; error?: string }>(
    'c01',
    `/api/floorplans/status/${jobId}`,
  );

export const selectFloorPlan = (jobId: string, variant: string) =>
  post<C01FullDesignPackage>('c01', '/api/select-plan', {
    job_id: jobId,
    selected_variant: variant,
  });

/** Sri Lanka's districts map 1:1 onto provinces — C01's building_schema_json
 *  carries district but not province, and C04's delay model needs the exact
 *  " Province"-suffixed string. Derived here rather than added to C01, since
 *  it's a pure lookup with no real design decision behind it. */
const DISTRICT_TO_PROVINCE: Record<string, string> = {
  Colombo: 'Western Province', Gampaha: 'Western Province', Kalutara: 'Western Province',
  Kandy: 'Central Province', Matale: 'Central Province', 'Nuwara Eliya': 'Central Province',
  Galle: 'Southern Province', Matara: 'Southern Province', Hambantota: 'Southern Province',
  Jaffna: 'Northern Province', Kilinochchi: 'Northern Province', Mannar: 'Northern Province',
  Vavuniya: 'Northern Province', Mullaitivu: 'Northern Province',
  Batticaloa: 'Eastern Province', Ampara: 'Eastern Province', Trincomalee: 'Eastern Province',
  Kurunegala: 'North Western Province', Puttalam: 'North Western Province',
  Anuradhapura: 'North Central Province', Polonnaruwa: 'North Central Province',
  Badulla: 'Uva Province', Monaragala: 'Uva Province',
  Ratnapura: 'Sabaragamuwa Province', Kegalle: 'Sabaragamuwa Province',
};

export const provinceForDistrict = (district: string | undefined | null): string | null =>
  (district && DISTRICT_TO_PROVINCE[district]) || null;

/** Maps C01's real building_schema_json (from /select-plan) onto the
 *  BuildingSchema shape every step after this one already consumes —
 *  field names already match almost exactly (see schema_serialiser.py),
 *  this only adds the derived province and drops C01's informational _meta. */
export function toBuildingSchema(raw: Record<string, unknown>): BuildingSchema {
  const district = (raw.district as string | undefined) ?? null;
  return {
    footprint_sqm: Number(raw.footprint_sqm ?? 0),
    perimeter: Number(raw.perimeter ?? 0),
    floors: Number(raw.floors ?? 1),
    floor_height: Number(raw.floor_height ?? 3),
    wall_height: Number(raw.wall_height ?? 3),
    excavation_depth: Number(raw.excavation_depth ?? 1.5),
    column_count: Number(raw.column_count ?? 0),
    openings_sqm: Number(raw.openings_sqm ?? 0),
    internal_wall_length: Number(raw.internal_wall_length ?? 0),
    finish_grade: (raw.finish_grade as BuildingSchema['finish_grade']) ?? 'mid',
    roof_type: (raw.roof_type as BuildingSchema['roof_type']) ?? 'gable',
    district,
    province: provinceForDistrict(district),
    is_coastal: Boolean(raw.is_coastal),
    terrain: (raw.terrain as BuildingSchema['terrain']) ?? 'flat',
    road_access: (raw.road_access as BuildingSchema['road_access']) ?? 'paved',
    plot_area: Number(raw.plot_area ?? 0),
    rooms: (raw.rooms as Record<string, number>) ?? {},
    bathroom_count: Number(raw.bathroom_count ?? 0),
    room_count: Number(raw.room_count ?? 0),
    base_rate_date: String(raw.base_rate_date ?? new Date().toISOString().slice(0, 10)),
    target_date: (raw.target_date as string | undefined) ?? null,
  };
}

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
