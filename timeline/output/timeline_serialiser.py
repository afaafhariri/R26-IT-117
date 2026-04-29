import uuid
from datetime import datetime, date
from builtins import dict
from timeline.pipeline import phases

class TimelineSerialiser:
    """
    Serializes timeline information into the final Timeline JSON payload.
    """

    def serialise(self, phase_durations: dict, critical_path: dict, gantt: list, building_schema: dict, cost_report: dict) -> dict[str, any]:
        """
        Structures output payload for Component 05 and Database storage.
        
        Args:
            phase_durations: map of phase -> working days.
            critical_path: dictionary from CriticalPathEngine.
            gantt: GanttBuilder JSON output.
            building_schema: Initial request payload (Building).
            cost_report: Initial request payload (Cost).
            
        Returns:
            dict containing full Timeline data.
        """
        try:
            timeline_id = str(uuid.uuid4())
            project_id = building_schema.get("project_id", "UNKNOWN_PROJECT_ID")
            generated_at = datetime.utcnow().isoformat()

            # find dates from gantt structure by searching the specific phase
            def get_phase_end(phase_name):
                for p in gantt:
                    if p["phase"] == phase_name:
                        return p["end_date"].isoformat() if isinstance(p["end_date"], date) else None
                return None
            
            project_start_date = None
            if gantt:
                project_start_date = min(g["start_date"] for g in gantt)
                projected_completion_date = max(g["end_date"] for g in gantt)
            else:
                project_start_date = date.today()
                projected_completion_date = date.today()

            # Format milestone dates explicitly based on known project steps
            milestone_dates = {
                "foundation_complete": get_phase_end(phases.FOUNDATION),
                "structure_complete": get_phase_end(phases.SUPERSTRUCTURE),
                "roof_complete": get_phase_end(phases.ROOF_COVERING),
                "fit_out_complete": get_phase_end(phases.FLOOR_FINISHING), # Assuming floor finishing is fit-out completion point here
                "handover": projected_completion_date.isoformat() if isinstance(projected_completion_date, date) else None
            }

            result = {
                "timeline_id": timeline_id,
                "project_id": project_id,
                "generated_at": generated_at,
                "summary": {
                    "total_duration_days": critical_path.get("total_duration_days"),
                    "total_duration_weeks": critical_path.get("total_duration_weeks"),
                    "projected_start_date": project_start_date.isoformat() if isinstance(project_start_date, date) else None,
                    "projected_completion_date": projected_completion_date.isoformat() if isinstance(projected_completion_date, date) else None,
                    "critical_path_phases": critical_path.get("critical_path", []),
                    "total_phases": len(phases.ALL_PHASES)
                },
                "phases": [
                    {
                        "phase": g["phase"],
                        "start_date": g["start_date"].isoformat() if isinstance(g["start_date"], date) else None,
                        "end_date": g["end_date"].isoformat() if isinstance(g["end_date"], date) else None,
                        "duration_days": g["duration_days"],
                        "is_critical": g["is_critical"],
                        "dependencies": g["dependencies"],
                        "float_days": g["float_days"]
                    } for g in gantt
                ],
                "milestone_dates": milestone_dates
            }

            return result

        except Exception as e:
            raise ValueError(f"Error serializing timeline: {str(e)}")
