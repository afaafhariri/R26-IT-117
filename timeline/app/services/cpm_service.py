"""Critical Path Method service for the construction schedule."""


TASK_DEPENDENCIES = [
    {"task": "foundation", "depends_on": []},
    {"task": "structure", "depends_on": ["foundation"]},
    {"task": "roofing", "depends_on": ["structure"]},
    {"task": "electrical_plumbing", "depends_on": ["structure"]},
    {"task": "finishing", "depends_on": ["roofing", "electrical_plumbing"]},
]

DAY_TASK_DEPENDENCIES = [
    {"task": "foundation", "depends_on": []},
    {"task": "structure", "depends_on": ["foundation"]},
    {"task": "masonry", "depends_on": ["structure"]},
    {"task": "roofing", "depends_on": ["structure"]},
    {"task": "electrical", "depends_on": ["masonry"]},
    {"task": "plumbing", "depends_on": ["masonry"]},
    {"task": "plastering", "depends_on": ["masonry"]},
    {"task": "finishing", "depends_on": ["roofing", "electrical", "plumbing", "plastering"]},
    {"task": "painting", "depends_on": ["finishing"]},
    {"task": "external_work", "depends_on": ["structure"]},
    {"task": "handover", "depends_on": ["painting", "external_work"]},
]


def get_task_dependencies() -> list[dict[str, list[str] | str]]:
    """Return the fixed residential construction dependency structure."""

    return TASK_DEPENDENCIES


def get_day_task_dependencies() -> list[dict[str, list[str] | str]]:
    """Return detailed dependency structure for Random Forest day predictions."""

    return DAY_TASK_DEPENDENCIES


def calculate_cpm(phase_durations: dict[str, int]) -> dict:
    """
    Calculate earliest start/finish weeks and the critical path.

    Two dependent paths are compared:
    1. foundation -> structure -> roofing -> finishing
    2. foundation -> structure -> electrical_plumbing -> finishing
    """

    foundation = phase_durations["foundation"]
    structure = phase_durations["structure"]
    roofing = phase_durations["roofing"]
    electrical_plumbing = phase_durations["electrical_plumbing"]
    finishing = phase_durations["finishing"]

    path_roofing = foundation + structure + roofing + finishing
    path_mep = foundation + structure + electrical_plumbing + finishing

    if path_roofing >= path_mep:
        critical_path = ["foundation", "structure", "roofing", "finishing"]
        total_duration = path_roofing
    else:
        critical_path = [
            "foundation",
            "structure",
            "electrical_plumbing",
            "finishing",
        ]
        total_duration = path_mep

    start_finish = _calculate_start_finish_weeks(phase_durations)

    return {
        "critical_path": critical_path,
        "total_project_duration_weeks": int(total_duration),
        "start_finish": start_finish,
    }


def _calculate_start_finish_weeks(phase_durations: dict[str, int]) -> dict[str, dict[str, int]]:
    """Calculate week ranges from the fixed dependency graph."""

    foundation_start = 1
    foundation_end = foundation_start + phase_durations["foundation"] - 1

    structure_start = foundation_end + 1
    structure_end = structure_start + phase_durations["structure"] - 1

    roofing_start = structure_end + 1
    roofing_end = roofing_start + phase_durations["roofing"] - 1

    mep_start = structure_end + 1
    mep_end = mep_start + phase_durations["electrical_plumbing"] - 1

    finishing_start = max(roofing_end, mep_end) + 1
    finishing_end = finishing_start + phase_durations["finishing"] - 1

    return {
        "foundation": {"start_week": foundation_start, "end_week": foundation_end},
        "structure": {"start_week": structure_start, "end_week": structure_end},
        "roofing": {"start_week": roofing_start, "end_week": roofing_end},
        "electrical_plumbing": {"start_week": mep_start, "end_week": mep_end},
        "finishing": {"start_week": finishing_start, "end_week": finishing_end},
    }


def calculate_cpm_days(phase_days: dict[str, int]) -> dict:
    """Calculate CPM for detailed day-level Random Forest predictions."""

    dependencies = {
        item["task"]: item["depends_on"] for item in DAY_TASK_DEPENDENCIES
    }
    order = [item["task"] for item in DAY_TASK_DEPENDENCIES]

    start_finish: dict[str, dict[str, int]] = {}
    for task in order:
        predecessors = dependencies[task]
        start_day = (
            max(start_finish[pred]["end_day"] for pred in predecessors) + 1
            if predecessors
            else 1
        )
        end_day = start_day + int(phase_days[task]) - 1
        start_finish[task] = {"start_day": start_day, "end_day": end_day}

    # Dynamic programming for longest path ending at each task.
    longest_path_duration: dict[str, int] = {}
    longest_path_nodes: dict[str, list[str]] = {}
    for task in order:
        if not dependencies[task]:
            longest_path_duration[task] = phase_days[task]
            longest_path_nodes[task] = [task]
            continue

        best_pred = max(
            dependencies[task],
            key=lambda pred: longest_path_duration[pred],
        )
        longest_path_duration[task] = (
            longest_path_duration[best_pred] + phase_days[task]
        )
        longest_path_nodes[task] = longest_path_nodes[best_pred] + [task]

    end_task = max(order, key=lambda task: start_finish[task]["end_day"])
    total_duration_days = start_finish[end_task]["end_day"]

    return {
        "critical_path": longest_path_nodes[end_task],
        "total_project_duration_days": int(total_duration_days),
        "total_project_duration_weeks": round(total_duration_days / 7, 2),
        "start_finish": start_finish,
    }
