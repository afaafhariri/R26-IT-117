from datetime import date, timedelta
import holidays
from typing import Dict, List
from timeline.pipeline import phases

class GanttBuilder:
    """
    Constructs an interactive Gantt chart representation of the construction timeline
    by translating working days to calendar dates, skipping weekends and holidays.
    """

    def __init__(self):
        # Set up Sri Lankan holidays
        self.sl_holidays = holidays.country_holidays("LK")

    def _add_working_days(self, start_date: date, days_to_add: int) -> date:
        """
        Adds a given number of working days to a starting date, avoiding weekends and SL public holidays.
        """
        current_date = start_date
        days_added = 0

        # We start on current_date, so we take 1 day
        # e.g. adding 0 days just puts us on the same day.
        if days_to_add == 0:
            return current_date

        while days_added < days_to_add:
            current_date += timedelta(days=1)
            # 5 is Saturday, 6 is Sunday in Python's weekday()
            is_weekend = current_date.weekday() >= 5
            is_holiday = current_date in self.sl_holidays
            
            if not is_weekend and not is_holiday:
                days_added += 1

        return current_date

    def build(self, phase_durations: Dict[str, int], critical_path_result: dict, project_start_date: date) -> List[dict]:
        """
        Builds Gantt chart data objects.
        
        Args:
            phase_durations: Dictionary of phase to duration.
            critical_path_result: Result from CriticalPathEngine.
            project_start_date: Project's initial start date.
            
        Returns:
            list[dict]: Gantt JSON structure.
        """
        try:
            gantt_data = []

            early_starts = critical_path_result["early_start_per_phase"]
            # early_finishes = critical_path_result["early_finish_per_phase"] # Not strictly needed if derived calendar date
            float_times = critical_path_result["float_per_phase"]
            critical_nodes = critical_path_result["critical_path"]
            
            # Dependencies required for Gantt display
            deps_map = {
                phases.SITE_PREPARATION: [],
                phases.FOUNDATION: [phases.SITE_PREPARATION],
                phases.SUPERSTRUCTURE: [phases.FOUNDATION],
                phases.BRICKWORK_AND_BLOCKWORK: [phases.SUPERSTRUCTURE],
                phases.ROOF_STRUCTURE: [phases.SUPERSTRUCTURE],
                phases.ROOF_COVERING: [phases.ROOF_STRUCTURE],
                phases.EXTERNAL_PLASTERING: [phases.BRICKWORK_AND_BLOCKWORK],
                phases.INTERNAL_PLASTERING: [phases.BRICKWORK_AND_BLOCKWORK],
                phases.FLOOR_FINISHING: [phases.INTERNAL_PLASTERING],
                phases.CEILING: [phases.INTERNAL_PLASTERING, phases.ELECTRICAL_FIRST_FIX, phases.PLUMBING_FIRST_FIX],
                phases.DOOR_AND_WINDOW_FIXING: [phases.FLOOR_FINISHING],
                phases.ELECTRICAL_FIRST_FIX: [], # Needs predecessor, usually Structure
                phases.PLUMBING_FIRST_FIX: [],
                phases.PAINTING: [phases.EXTERNAL_PLASTERING],
                phases.ELECTRICAL_SECOND_FIX: [phases.CEILING],
                phases.PLUMBING_SECOND_FIX: [phases.CEILING],
                phases.EXTERNAL_WORKS: [],
                phases.FINAL_INSPECTION: [
                    phases.DOOR_AND_WINDOW_FIXING, 
                    phases.ELECTRICAL_SECOND_FIX, 
                    phases.PLUMBING_SECOND_FIX, 
                    phases.EXTERNAL_WORKS
                ]
            }

            for phase in phases.ALL_PHASES:
                duration_days = phase_durations.get(phase, 0)
                early_start_days = early_starts.get(phase, 0)
                float_days = float_times.get(phase, 0)
                is_critical = phase in critical_nodes
                
                # Derive calendar start date by pushing project_start_date forward 'early_start_days'
                phase_start_date = self._add_working_days(project_start_date, early_start_days)
                
                # End date is start_date + (duration - 1) working days
                # E.g. a 1-day task starting Monday finishes on Monday.
                phase_end_date = self._add_working_days(phase_start_date, duration_days - 1 if duration_days > 0 else 0)

                gantt_data.append({
                    "phase": phase,
                    "start_date": phase_start_date,
                    "end_date": phase_end_date,
                    "duration_days": duration_days,
                    "is_critical": is_critical,
                    "dependencies": deps_map.get(phase, []),
                    "float_days": float_days
                })

            return gantt_data

        except Exception as e:
            raise ValueError(f"Error building Gantt data: {str(e)}")
