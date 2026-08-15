"""
Shared phase name constants for Component 04 — Timeline Generation.

Every module (schedule_model, critical_path, gantt_builder, timeline_serialiser)
imports phase names exclusively from here so that a rename is a one-line change.
"""

# ── Individual phase name constants ──────────────────────────────────────────

SITE_PREPARATION        = "site_preparation"
FOUNDATION              = "foundation"
SUPERSTRUCTURE          = "superstructure"
BRICKWORK_AND_BLOCKWORK = "brickwork_and_blockwork"
ROOF_STRUCTURE          = "roof_structure"
ROOF_COVERING           = "roof_covering"
EXTERNAL_PLASTERING     = "external_plastering"
INTERNAL_PLASTERING     = "internal_plastering"
FLOOR_FINISHING         = "floor_finishing"
DOOR_AND_WINDOW_FIXING  = "door_and_window_fixing"
ELECTRICAL_FIRST_FIX    = "electrical_first_fix"
PLUMBING_FIRST_FIX      = "plumbing_first_fix"
CEILING                 = "ceiling"
PAINTING                = "painting"
ELECTRICAL_SECOND_FIX   = "electrical_second_fix"
PLUMBING_SECOND_FIX     = "plumbing_second_fix"
EXTERNAL_WORKS          = "external_works"
FINAL_INSPECTION        = "final_inspection"

# ── Ordered list of all 18 phases ─────────────────────────────────────────────

ALL_PHASES: list[str] = [
    SITE_PREPARATION,
    FOUNDATION,
    SUPERSTRUCTURE,
    BRICKWORK_AND_BLOCKWORK,
    ROOF_STRUCTURE,
    ROOF_COVERING,
    EXTERNAL_PLASTERING,
    INTERNAL_PLASTERING,
    FLOOR_FINISHING,
    DOOR_AND_WINDOW_FIXING,
    ELECTRICAL_FIRST_FIX,
    PLUMBING_FIRST_FIX,
    CEILING,
    PAINTING,
    ELECTRICAL_SECOND_FIX,
    PLUMBING_SECOND_FIX,
    EXTERNAL_WORKS,
    FINAL_INSPECTION,
]

# ── Predecessor dependency graph ──────────────────────────────────────────────
# {phase: [immediate predecessors]}
# electrical_first_fix and plumbing_first_fix have no structural predecessors
# in this model — they run in parallel once the site is active.
# external_works also runs in parallel.

PHASE_DEPENDENCIES: dict[str, list[str]] = {
    SITE_PREPARATION:        [],
    FOUNDATION:              [SITE_PREPARATION],
    SUPERSTRUCTURE:          [FOUNDATION],
    BRICKWORK_AND_BLOCKWORK: [SUPERSTRUCTURE],
    ROOF_STRUCTURE:          [SUPERSTRUCTURE],
    ROOF_COVERING:           [ROOF_STRUCTURE],
    EXTERNAL_PLASTERING:     [BRICKWORK_AND_BLOCKWORK],
    INTERNAL_PLASTERING:     [BRICKWORK_AND_BLOCKWORK],
    FLOOR_FINISHING:         [INTERNAL_PLASTERING],
    DOOR_AND_WINDOW_FIXING:  [FLOOR_FINISHING],
    ELECTRICAL_FIRST_FIX:    [],
    PLUMBING_FIRST_FIX:      [],
    CEILING:                 [INTERNAL_PLASTERING, ELECTRICAL_FIRST_FIX, PLUMBING_FIRST_FIX],
    PAINTING:                [EXTERNAL_PLASTERING],
    ELECTRICAL_SECOND_FIX:   [CEILING],
    PLUMBING_SECOND_FIX:     [CEILING],
    EXTERNAL_WORKS:          [],
    FINAL_INSPECTION:        [
        DOOR_AND_WINDOW_FIXING,
        ELECTRICAL_SECOND_FIX,
        PLUMBING_SECOND_FIX,
        EXTERNAL_WORKS,
    ],
}

# ── Milestone phases ──────────────────────────────────────────────────────────
# Maps milestone label -> the phase whose end_date marks that milestone.

MILESTONE_PHASES: dict[str, str] = {
    "foundation_complete": FOUNDATION,
    "structure_complete":  SUPERSTRUCTURE,
    "roof_complete":       ROOF_COVERING,
    "fit_out_complete":    CEILING,
    "handover":            FINAL_INSPECTION,
}
