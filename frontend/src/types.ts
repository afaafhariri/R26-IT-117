// Mirror of Architecture/models/schemas.py — keep names identical to backend.

export interface CadastralData {
  land_area_perches: number
  land_area_sqft: number
  district: string
  road_access_type: string
  gps_coordinates: [number, number][]
  sld99_coordinates: [number, number][]
  plot_boundary_polygon: [number, number][]
  orientation: string
  raw_ocr_text: string
  extracted_entities: Record<string, unknown>
}

export interface BuildableZone {
  buildable_polygon: [number, number][]
  buildable_area_sqft: number
  bcr_value: number
  front_setback_ft: number
  rear_setback_ft: number
  side_setbacks_ft: number[]
  constraints_summary: string
}

export interface Room {
  name: string
  width_ft: number
  length_ft: number
  area_sqft: number
  position_x: number
  position_y: number
  adjacencies: string[]
  has_window: boolean
  has_door: boolean
}

export interface FloorPlanScores {
  space_utilisation: number
  natural_light: number
  adjacency: number
  ventilation: number
  overall: number
}

export interface FloorPlanAlternative {
  variant: 'conservative' | 'balanced' | 'creative'
  temperature_used: number
  rooms: Room[]
  total_built_area_sqft: number
  scores: FloorPlanScores
  validation_passed: boolean
  description: string
}

export interface ShoppingItem {
  name: string
  description: string
  price_range_lkr: string
  category: 'furniture' | 'lighting' | 'flooring' | 'fixtures' | 'decor'
}

export interface VisualizationAssets {
  exterior_image_base64: string
  interior_image_base64: string
  blueprint_2d_image_base64: string
  floorplan_3d_image_base64: string
  blueprint_2d_description: string
  floorplan_3d_description: string
  walkthrough_script: string
  shopping_list: ShoppingItem[]
  video_url: string | null
  video_skipped_reason: string | null
}

export interface StageLogEntry {
  stage: string
  message: string
  timestamp: string
}

export interface FullDesignPackage {
  job_id: string
  cadastral_data: CadastralData
  buildable_zone: BuildableZone
  selected_plan: FloorPlanAlternative
  svg_floor_plan_url: string
  pdf_report_url: string
  building_schema_json: Record<string, unknown>
  visualization_assets: VisualizationAssets
  generation_stages_log: StageLogEntry[]
}

// App state
export type AppView = 'upload' | 'land-review' | 'plan-selection' | 'generating' | 'results'

export interface AppState {
  currentView: AppView
  jobId: string | null
  cadastralData: CadastralData | null
  buildableZone: BuildableZone | null
  floorPlanAlternatives: FloorPlanAlternative[]
  selectedVariant: 'conservative' | 'balanced' | 'creative' | null
  generationLog: string[]
  fullDesignPackage: FullDesignPackage | null
  error: string | null
  theme: 'light' | 'dark'
}
