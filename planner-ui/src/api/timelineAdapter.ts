import type { BuildingSchema, CostReport, TimelineResponse } from '../types';

export interface TimelinePredictionInputs {
  floorsToBuild: number;
  startDate: string;
  scopeDescription?: string;
}

export type C03DisplayTimeline = TimelineResponse;

/** Forward the costed BOQ so the 11-activity model uses C02 quantities. */
export function buildC03Request(
  building: BuildingSchema,
  estimate: CostReport,
  inputs: TimelinePredictionInputs,
  projectId: string,
  projectName: string,
) {
  const plannedFloors = building.floors;
  if (!Number.isInteger(plannedFloors) || plannedFloors < 1 ||
      !Number.isInteger(inputs.floorsToBuild) || inputs.floorsToBuild < 1 ||
      inputs.floorsToBuild > plannedFloors) {
    throw new Error('Required floors must be between 1 and the planned total floors.');
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(inputs.startDate)) {
    throw new Error('Choose a valid planned start date.');
  }

  return {
    estimate_id: estimate.estimate_id,
    project_id: projectId,
    project_name: projectName,
    planned_start_date: inputs.startDate,
    district: building.district || estimate.rate_metadata.district,
    province: building.province || estimate.rate_metadata.province,
    building_type: 'residential',
    floors: plannedFloors,
    room_count: building.room_count,
    bathroom_count: building.bathroom_count,
    construction_scope: {
      planned_total_floors: plannedFloors,
      timeline_required_floors: inputs.floorsToBuild,
      scope_type: inputs.floorsToBuild === plannedFloors ? 'full_construction' : 'partial_construction',
      scope_description: inputs.scopeDescription?.trim() || '',
    },
    summary: estimate.summary,
    boq_summary: estimate.boq_summary,
    trade_breakdown: estimate.trade_breakdown,
    risk_factors_applied: estimate.risk_factors_applied,
    model_metadata: estimate.model_metadata,
    rate_metadata: estimate.rate_metadata,
    feeds_downstream: estimate.feeds_downstream,
  };
}

export function adaptC03Response(raw: TimelineResponse): C03DisplayTimeline {
  if (!Array.isArray(raw.gantt_chart_data) || raw.gantt_chart_data.length !== 11 ||
      !Array.isArray(raw.critical_path) || !Array.isArray(raw.milestones) ||
      !raw.predicted_phase_durations_weeks || !Number.isFinite(raw.total_project_duration_days) ||
      !raw.performance_monitoring_payload || raw.performance_monitoring_payload.phases.length !== 11) {
    throw new Error('C03 returned an incomplete 11-activity schedule. No prediction was displayed.');
  }
  return raw;
}
