// Types mirroring the live API responses of C02 (:8002), C03 (:8000) and C04 (:5004).
// Field names/shapes were taken from real captured responses, not from docs.

/* ─────────────────────────── Step 1 — Architecture (C01) ─────────────────────────
 * C01 is not wired up yet. Its only downstream output is BuildingSchema, so step 1
 * is a local stub that produces one. Swapping in the real C01 calls later changes
 * nothing below this line. */

export type FinishGrade = 'economy' | 'mid' | 'luxury';
export type RoofType = 'flat' | 'gable' | 'hip' | 'mansard';
export type Terrain = 'flat' | 'sloped' | 'hilly' | 'rocky';
export type RoadAccess = 'paved' | 'gravel' | 'track' | 'none';

export interface BuildingSchema {
  footprint_sqm: number;
  perimeter: number;
  floors: number;
  floor_height: number;
  wall_height: number;
  excavation_depth: number;
  column_count: number;
  openings_sqm: number;
  internal_wall_length: number;
  finish_grade: FinishGrade;
  roof_type: RoofType;
  /** Flows all the way through to C04 — do not drop it. */
  district?: string | null;
  province?: string | null;
  is_coastal: boolean;
  terrain: Terrain;
  road_access: RoadAccess;
  plot_area: number;
  rooms: Record<string, number>;
  bathroom_count: number;
  room_count: number;
  /** { boqPartKey: materialKey } — chosen in step 2. */
  materials?: Record<string, string>;
  base_rate_date: string;
  target_date?: string | null;
}

/* ───────────────────────── Step 2 — Cost Estimation (C02) ───────────────────── */

export interface MaterialVariant {
  material: string;
  description: string;
  unit: string;
  rate_lkr: number;
  rate_source: string;
  last_updated: string;
}

/** GET /materials → { boqPartKey: variants[] } */
export type MaterialCatalog = Record<string, MaterialVariant[]>;

export interface CostSummary {
  total_lkr: number;
  lower_bound_lkr: number;
  upper_bound_lkr: number;
  cost_per_sqm_lkr: number;
  confidence_level: number;
  ml_point_estimate_lkr: number;
  direct_cost_lkr: number;
}

export interface ShapDriver {
  feature: string;
  impact_lkr: number;
  direction: 'increases' | 'decreases';
}

export interface ContingencyLine {
  item: string;
  rate_pct: number;
  amount_lkr: number;
  cumulative_lkr: number;
}

export interface TradeLine {
  line_cost_lkr?: number;
  quantity?: number;
  unit?: string;
  rate_lkr?: number;
  [k: string]: unknown;
}

export interface RateMetadata {
  escalation_factor: number;
  base_date: string;
  target_date: string;
  /** Added so location survives C01 → C02 → C03 → C04. */
  district: string;
  province: string;
}

export interface FeedsDownstream {
  total_labour_days: number;
  structural_complexity_score: number;
  trade_value_breakdown: Record<string, number>;
  floor_area_sqm: number;
  bathroom_count: number;
}

export interface CostReport {
  estimate_id: string;
  generated_at: string;
  summary: CostSummary;
  boq_summary: Record<string, unknown>;
  trade_breakdown: Record<string, TradeLine>;
  material_options: {
    selections: Record<string, unknown>;
    alternatives: Record<string, unknown>;
  };
  contingency_breakdown: ContingencyLine[];
  risk_factors_applied: unknown[];
  shap_top_drivers: ShapDriver[];
  model_metadata: Record<string, unknown>;
  rate_metadata: RateMetadata;
  feeds_downstream: FeedsDownstream;
}

/* ─────────────────────────── Step 3 — Timeline (C03) ───────────────────────── */

export interface GanttTask {
  id: number;
  task: string;
  start_date: string | null;
  end_date: string | null;
  start_week: number;
  end_week: number;
  duration_weeks: number;
  duration_days: number | null;
}

export interface Milestone {
  name: string;
  phase: string;
  week: number;
}

export interface TaskDependency {
  task: string;
  depends_on: string[];
}

/** The exact body C04's POST /schedule expects. Pass it through untouched. */
export interface SchedulePayload {
  project: {
    name: string;
    district: string;
    province: string;
    floors: number;
    building_type: string;
  };
  phases: {
    phase_id: number;
    phase_group: string;
    sub_phase: string;
    planned_start: string;
    planned_end: string;
    planned_duration_days: number;
    sequence: number;
  }[];
  project_id?: string;
  planned_start_date?: string;
  planned_end_date?: string;
  total_planned_duration_days?: number;
  [k: string]: unknown;
}

export interface TimelineResponse {
  project_id: string;
  project_name: string;
  predicted_phase_durations_days?: Record<string, number> | null;
  predicted_phase_durations_weeks: Record<string, number>;
  total_project_duration_days?: number | null;
  total_project_duration_weeks: number;
  input_summary?: Record<string, number | string | null> | null;
  critical_path: string[];
  milestones: Milestone[];
  gantt_chart_data: GanttTask[];
  task_dependencies: TaskDependency[];
  resource_allocation_plan: Record<string, Record<string, unknown>>;
  performance_monitoring_payload?: SchedulePayload | null;
  confidence_score: number;
  message: string;
}

/* ──────────────────────── Step 4 — Performance (C04) ───────────────────────── */

export const DELAY_CATEGORIES = [
  'Labour',
  'Material Supply & Quality',
  'Environmental & Site',
  'Financial & Funding',
  'Design & Technical',
  'Land & Legal',
  'Owner / Social / Behavioural',
] as const;
export type DelayCategory = (typeof DELAY_CATEGORIES)[number];

export const LABOUR_AVAILABILITY = ['Very Low', 'Low', 'Medium', 'Good', 'Full'] as const;
export type LabourAvailability = (typeof LABOUR_AVAILABILITY)[number];

export const MATERIAL_SUPPLY = ['Yes', 'No'] as const;
export type MaterialSupply = (typeof MATERIAL_SUPPLY)[number];

export const WEATHER_SEVERITY = ['No disruption', 'Minor', 'Moderate', 'Severe'] as const;
export type WeatherSeverity = (typeof WEATHER_SEVERITY)[number];

export interface ScheduleCreated {
  success: true;
  project_id: number;
  phases_created: number;
  phase_ids: number[];
  message: string;
}

export interface SpiResponse {
  success: true;
  project_id: number;
  phase_id: number;
  progress_update_id: number;
  spi_id: number;
  planned_percent: number;
  actual_percent: number;
  spi_value: number;
  alert_level: 'OK' | 'WARNING' | 'CRITICAL' | string;
  /** True when alert_level is WARNING or CRITICAL — run the predict step next. */
  requires_prediction_step: boolean;
  message: string;
}

/** One retrieved historical case from C04's FAISS-backed RAG pipeline.
 *  `score` is a raw vector-distance metric (lower = more similar) - it is
 *  NOT a percentage or confidence score, and must never be presented as one. */
export interface SimilarCase {
  rank: number;
  case: string;
  score: number;
  cause_of_delay?: string | null;
  corrective_action_taken?: string | null;
  construction_status?: string | null;
  summary?: string | null;
}

export interface PredictResponse {
  success: true;
  project_id: number;
  phase_id: number;
  spi_id: number;
  alert_level: string;
  prediction_id: number;
  prediction: {
    delay_risk: string;
    estimated_delay_days: number;
    confidence: number;
    risk_probabilities: Record<string, number>;
  };
  weather_used: {
    source: string;
    weather_severity: string | null;
    temperature_c?: number | null;
    condition?: string | null;
    rainfall_mm?: number | null;
    error?: string | null;
  };
  similar_cases: SimilarCase[];
  recommendation_id: number | null;
  recommendation: {
    explanation?: string | null;
    corrective_actions?: string[] | string | null;
  };
  notifications: { sent_to_c02: boolean; sent_to_c03: boolean; errors: string[] };
  message: string;
}

/** GET /project/<id>/weather - exact shape, nothing invented. `source` is
 *  "live" (real OpenWeatherMap reading) or "fallback" (key missing / call
 *  failed / no data yet) - never display a fallback value as if it were live. */
export interface WeatherResponse {
  success: boolean;
  project_id: number;
  weather: {
    success: boolean;
    source: 'live' | 'fallback' | string;
    location_source: 'coordinates' | 'district' | string;
    district?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    temperature_c: number | null;
    condition: string | null;
    rainfall_mm: number | null;
    wind_mps: number | null;
    weather_severity: string | null;
    error?: string | null;
  };
}

/** PATCH /project/<id>/location - exact shape. Request body is exactly
 *  { latitude, longitude } - no other fields, matching the backend's
 *  existing validation exactly. */
export interface LocationUpdateResponse {
  success: boolean;
  project_id: number;
  latitude: number;
  longitude: number;
  message: string;
}

export interface DashboardPhase {
  phase_id: number;
  phase_group: string;
  sub_phase: string;
  sequence: number;
  planned_start: string | null;
  planned_end: string | null;
  planned_duration_days: number | null;
  expected_progress_percent: number;
  actual_percent: number | null;
  schedule_status: string;
  status: string;
  latest_spi: number | null;
  latest_progress: unknown | null;
}

/** One row from GET /project/<id>/dashboard's `progress_history` - real
 *  field names from the actual SQL query (dashboard_feed.py), newest first
 *  (backend orders by created_at DESC). */
export interface ProgressHistoryEntry {
  update_id: number;
  phase_id: number;
  update_date: string | null;
  planned_percent: number;
  actual_percent: number;
  spi_value: number | null;
  alert_level: string | null;
  entered_by: string | null;
}

export interface Dashboard {
  success: true;
  project: {
    project_id: number;
    name: string;
    district: string;
    province: string;
    floors: number;
    building_type: string;
    latitude: number | null;
    longitude: number | null;
  };
  phases: DashboardPhase[];
  progress_history: ProgressHistoryEntry[];
  active_alerts: { message?: string; alert_type?: string; [k: string]: unknown }[];
  latest_prediction: unknown | null;
  latest_recommendation: unknown | null;
  project_summary: {
    total_phases: number;
    completed_phases: number;
    overall_start: string | null;
    overall_end: string | null;
    total_duration_days: number | null;
  };
}

/* ──────────────────────────── Persisted run state ─────────────────────────── */

export interface ProgressEntry {
  phaseId: number;
  phaseLabel: string;
  actualPercent: number;
  spi: SpiResponse;
  prediction?: PredictResponse;
  at: string;
}

export interface RunState {
  runId: string;
  updatedAt: string;
  projectName: string;
  step1?: { buildingSchema: BuildingSchema; source: 'stub' | 'c01' };
  step2?: { estimate: CostReport; materials: Record<string, string> };
  step3?: { timeline: TimelineResponse; schedulePayload: SchedulePayload };
  step4?: { c04ProjectId: number; entries: ProgressEntry[] };
}
