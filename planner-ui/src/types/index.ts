// Types mirroring the live API responses of C02 (:8002), C03 (:8000) and C04 (:5004).
// Field names/shapes were taken from real captured responses, not from docs.

/* ─────────────────────────── Step 1 — Architecture (C01) ─────────────────────────
 * C01's only downstream output that matters here is BuildingSchema — everything
 * below in this section is C01's own request/response shapes (upload, land data,
 * floor plan generation, final package), which get mapped into a BuildingSchema
 * once a plan is picked. Swapping in a different C01 build later only means
 * matching these shapes; nothing past that mapping (Step 2 onward) changes. */

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

/** GET /api/process-cadastral response shapes (Architecture/models/schemas.py). */
export interface C01CadastralData {
  land_area_perches: number;
  land_area_sqft: number;
  district: string;
  road_access_type: string;
  gps_coordinates: [number, number][];
  sld99_coordinates: [number, number][];
  plot_boundary_polygon: [number, number][];
  orientation: string;
  raw_ocr_text: string;
  extracted_entities: Record<string, unknown>;
}

export interface C01BuildableZone {
  buildable_polygon: [number, number][];
  buildable_area_sqft: number;
  buildable_area_sqm?: number;
  max_floors?: number;
  bcr_value: number;
  front_setback_ft: number;
  rear_setback_ft: number;
  side_setbacks_ft: number[];
  constraints_summary: string;
}

export interface C01Room {
  name: string;
  floor: number;
  width_ft: number;
  length_ft: number;
  area_sqft: number;
  position_x: number;
  position_y: number;
  adjacencies: string[];
  has_window: boolean;
  has_door: boolean;
}

export interface C01FloorPlanScores {
  space_utilisation: number;
  natural_light: number;
  adjacency: number;
  ventilation: number;
  overall: number;
}

export interface C01FloorPlanAlternative {
  variant: 'conservative' | 'balanced' | 'creative';
  temperature_used: number;
  rooms: C01Room[];
  total_built_area_sqft: number;
  scores: C01FloorPlanScores;
  validation_passed: boolean;
  violations: string[];
  description: string;
}

export interface C01ShoppingItem {
  name: string;
  description: string;
  price_range_lkr: string;
  category: 'furniture' | 'lighting' | 'flooring' | 'fixtures' | 'decor';
}

export interface C01VisualizationAssets {
  exterior_image_base64: string;
  interior_image_base64: string;
  blueprint_2d_image_base64: string;
  blueprint_2d_description: string;
  floorplan_3d_image_base64: string;
  floorplan_3d_description: string;
  walkthrough_script: string;
  shopping_list: C01ShoppingItem[];
}

export interface C01FullDesignPackage {
  job_id: string;
  cadastral_data: C01CadastralData;
  buildable_zone: C01BuildableZone;
  selected_plan: C01FloorPlanAlternative;
  building_schema_json: Record<string, unknown>;
  visualization_assets: C01VisualizationAssets;
  video: unknown | null;
}

/** POST /api/generate-floorplans request body. */
export interface C01UserRequirements {
  bedrooms: number;
  bathrooms: number;
  living_room: boolean;
  kitchen: boolean;
  dining_room: boolean;
  garage: boolean;
  style: 'modern' | 'traditional' | 'minimalist' | 'colonial' | 'contemporary';
  floors: number;
  outdoor_features: string[];
  special_rooms: string[];
  additional_notes: string;
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
  /** C02's own 0-1 concrete ratio. NOT the 1.1-2.674 multiplier C03's model was
   *  trained on - C03 rejects this value and recomputes it. Do not display it as
   *  "the" complexity score; the timeline response reports the one actually used. */
  structural_complexity_score: number;
  trade_value_breakdown: Record<string, number>;
  floor_area_sqm: number;
  /** Storey count forwarded from the C01 schema. C03 reads it to size its model
   *  input and stamps it onto the project record it creates in C04. */
  floors: number;
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
