ALL_PHASES = [
    'Pre-Construction & Approvals',
    'Site Preparation',
    'Foundations',
    'Structure',
    'Envelope & Waterproofing',
    'MEP Rough-Ins',
    'Finishes',
    'External Works & Handover',
]

PHASE_DEPENDENCIES = {
    'Pre-Construction & Approvals': [],
    'Site Preparation':             ['Pre-Construction & Approvals'],
    'Foundations':                  ['Site Preparation'],
    'Structure':                    ['Foundations'],
    'Envelope & Waterproofing':     ['Structure'],
    'MEP Rough-Ins':                ['Envelope & Waterproofing'],
    'Finishes':                     ['MEP Rough-Ins'],
    'External Works & Handover':    ['Finishes'],
}

# (min_weeks, max_weeks) — model outputs are clamped to these bounds
PHASE_BOUNDS = {
    'Pre-Construction & Approvals': (2,  8),
    'Site Preparation':             (1,  4),
    'Foundations':                  (2,  8),
    'Structure':                    (4, 16),
    'Envelope & Waterproofing':     (2,  8),
    'MEP Rough-Ins':                (2,  6),
    'Finishes':                     (3, 10),
    'External Works & Handover':    (1,  4),
}

PHASE_SUBTASKS = {
    'Pre-Construction & Approvals': [
        'Site selection & surveying',
        'Soil investigation',
        'Architectural & structural design',
        'Authority approvals',
        'BOQ preparation & tendering',
    ],
    'Site Preparation': [
        'Site clearing & hoarding',
        'Temporary site office & services',
        'Earthworks & grading',
    ],
    'Foundations': [
        'Foundation work',
        'Ground beams',
        'Ground floor slab',
    ],
    'Structure': [
        'Columns & beams',
        'Floor slabs',
        'Upper floor structure',
        'Staircase',
        'Roof slab',
    ],
    'Envelope & Waterproofing': [
        'Masonry work',
        'Roof waterproofing',
        'Windows & doors',
        'External rendering',
    ],
    'MEP Rough-Ins': [
        'Electrical conduit work',
        'Plumbing & drainage',
        'AC installations',
        'Solar/LPG hot water systems',
    ],
    'Finishes': [
        'Internal plastering',
        'Tiling',
        'Painting',
        'Carpentry & joinery',
        'Kitchen & bathroom fittings',
        'MEP fixtures & testing',
    ],
    'External Works & Handover': [
        'Boundary wall & gate',
        'Landscaping',
        'Driveway & paving',
        'Final inspections',
        'Snagging & rectification',
        'Client handover',
    ],
}

# Maps each phase name to its CSV / model column name
PHASE_COLUMNS = {
    'Pre-Construction & Approvals': 'preconstruction_weeks',
    'Site Preparation':             'siteprep_weeks',
    'Foundations':                  'foundation_weeks',
    'Structure':                    'structure_weeks',
    'Envelope & Waterproofing':     'envelope_weeks',
    'MEP Rough-Ins':                'mep_weeks',
    'Finishes':                     'finishes_weeks',
    'External Works & Handover':    'external_weeks',
}

# Reverse: column name → display name
COLUMN_TO_PHASE = {v: k for k, v in PHASE_COLUMNS.items()}

# All target column names in order (used by train.py and the API pipeline)
TARGET_COLUMNS = [PHASE_COLUMNS[p] for p in ALL_PHASES]

# Phases that are key milestones for recommendations logic
MILESTONE_PHASES = ['Foundations', 'Structure', 'Finishes']

# Dashboard badge colours per phase
PHASE_COLORS = {
    'Pre-Construction & Approvals': '#6B7280',
    'Site Preparation':             '#EAB308',
    'Foundations':                  '#EF4444',
    'Structure':                    '#F97316',
    'Envelope & Waterproofing':     '#3B82F6',
    'MEP Rough-Ins':                '#8B5CF6',
    'Finishes':                     '#10B981',
    'External Works & Handover':    '#14B8A6',
}
