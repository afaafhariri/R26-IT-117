import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { BuildingSchema, C01BuildableZone, C01CadastralData, C01FloorPlanAlternative, C01FullDesignPackage, RunState } from '../types';
import { toBuildingSchema } from '../api/services';
import { UploadCadastral } from './step1/UploadCadastral';
import { DesignRequirements } from './step1/DesignRequirements';
import { ChooseFloorPlan } from './step1/ChooseFloorPlan';
import { GeneratingPackage } from './step1/GeneratingPackage';
import { DesignSummary } from './step1/DesignSummary';
import { LandPanel } from './step1/LandPanel';

/* Component 01 (Architecture) is now wired up for real:
 *   POST /process-cadastral → POST /generate-floorplans → poll
 *   GET /floorplans/status/{id} → POST /select-plan
 * FullDesignPackage.building_schema_json maps onto BuildingSchema via
 * toBuildingSchema() in api/services.ts — nothing downstream of step 1
 * changes regardless of which path produced the schema.
 *
 * "Load sample" below is kept as a secondary escape hatch for offline
 * dev/demo use (no C01 backend running) — the real flow is the default.
 *
 * Laid out after the Stitch "C01 CadaPlan Architectural Synthesis" screen.
 * That screen is one dashboard; C01 is a sequence of calls, so the same
 * header and stage strip frame each phase and the land panel stays beside
 * every phase once the deed has been read. */

/** Verified against the live C02 — returns ~17.7M LKR. */
const SAMPLE: BuildingSchema = {
  footprint_sqm: 120,
  perimeter: 44,
  floors: 2,
  floor_height: 3,
  wall_height: 3,
  excavation_depth: 1.5,
  column_count: 12,
  openings_sqm: 28,
  internal_wall_length: 36,
  finish_grade: 'mid',
  roof_type: 'gable',
  district: 'Galle',
  province: 'Southern Province',
  is_coastal: true,
  terrain: 'flat',
  road_access: 'paved',
  plot_area: 500,
  rooms: { bedroom: 3, bathroom: 2, living_room: 1, kitchen: 1 },
  bathroom_count: 2,
  room_count: 6,
  base_rate_date: '2024-10-01',
  target_date: '2027-08-26',
};

type Phase = 'upload' | 'requirements' | 'choose-plan' | 'generating-package' | 'summary';

const PHASE_TITLES: Record<Phase, string> = {
  upload: 'Upload cadastral plan',
  requirements: 'Design brief',
  'choose-plan': 'Floor plan synthesis alternatives',
  'generating-package': 'Building the design package',
  summary: 'Design package',
};

/** The stage strip. `at` is the stage the current phase is working on. */
const STAGES = [
  { n: '01', group: 'Extract', name: 'Deed reading', how: 'OCR + entity extraction' },
  { n: '02', group: 'Geometry', name: 'Buildable zone', how: 'NBC setbacks & coverage' },
  { n: '03', group: 'Brief', name: 'Design brief', how: 'Rooms, floors & style' },
  { n: '04', group: 'Synthesis', name: 'Floor plan options', how: 'Three layouts, scored' },
  { n: '05', group: 'Render', name: 'Design package', how: 'Renders & blueprint' },
  { n: '06', group: 'Handoff', name: 'To cost estimation', how: 'Building specification' },
];
const STAGE_AT: Record<Phase, number> = {
  upload: 0,
  requirements: 2,
  'choose-plan': 3,
  'generating-package': 4,
  summary: 5,
};

type Props = { run: RunState; update: (p: Partial<RunState>) => void };

export function Step1Design({ run, update }: Props) {
  const nav = useNavigate();
  const [phase, setPhase] = useState<Phase>('upload');

  const [jobId, setJobId] = useState<string | null>(null);
  const [cadastral, setCadastral] = useState<C01CadastralData | null>(null);
  const [zone, setZone] = useState<C01BuildableZone | null>(null);
  const [alternatives, setAlternatives] = useState<C01FloorPlanAlternative[]>([]);
  const [pkg, setPkg] = useState<C01FullDesignPackage | null>(null);
  const [packageError, setPackageError] = useState<string | null>(null);

  const finish = (
    schema: BuildingSchema,
    source: 'stub' | 'c01',
    projectName: string,
    designPackage?: C01FullDesignPackage,
  ) => {
    update({
      projectName,
      step1: { buildingSchema: schema, source, designPackage },
      // A changed design invalidates everything computed from it.
      step2: undefined,
      step3: undefined,
      step4: undefined,
    });
    nav('/step/2');
  };

  const loadSample = () => finish(SAMPLE, 'stub', run.projectName || 'My House');

  const at = STAGE_AT[phase];
  const land = pkg ? { c: pkg.cadastral_data, z: pkg.buildable_zone } : cadastral && zone ? { c: cadastral, z: zone } : null;

  return (
    <div className="cs">
      <div className="cs-head">
        <div>
          <span className="chip ink">C01 // Architectural synthesis</span>
          <h1>{PHASE_TITLES[phase]}</h1>
          <div className="meta">
            {land
              ? `${land.c.district} · ${land.c.land_area_perches.toFixed(2)} perches · ${land.c.road_access_type} access`
              : 'Upload a Sri Lankan survey plan to start a compliant design.'}
          </div>
        </div>
        <div className="cs-head-side">
          <div className="btn-row">
            <span className="chip">
              Regulations: <b>NBC Sri Lanka setbacks &amp; coverage</b>
            </span>
          </div>
          {phase === 'upload' && (
            <div className="btn-row">
              <button className="sm" onClick={loadSample}>
                Skip with sample data →
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="st-stages" role="list" aria-label="Design stages">
        {STAGES.map((s, i) => {
          const state = i < at ? 'done' : i === at ? 'active' : 'pending';
          return (
            <div className={`st-stage ${state}`} role="listitem" key={s.n}>
              <span className="eyebrow">
                {s.n} // {s.group}
              </span>
              <h3>{s.name}</h3>
              <p>{s.how}</p>
              <span className="foot">
                {state === 'done' ? 'Completed' : state === 'active' ? 'In progress' : 'Pending'}
              </span>
            </div>
          );
        })}
      </div>

      {phase === 'upload' && (
        <UploadCadastral
          onSample={loadSample}
          onSuccess={(res) => {
            setJobId(res.job_id);
            setCadastral(res.cadastral_data);
            setZone(res.buildable_zone);
            setPhase('requirements');
          }}
        />
      )}

      {phase === 'generating-package' && <GeneratingPackage />}

      {land && phase !== 'upload' && phase !== 'generating-package' && (
        <div className="st-split">
          <LandPanel cadastral={land.c} zone={land.z} />

          <div className="cs">
            {phase === 'requirements' && jobId && cadastral && zone && (
              <DesignRequirements
                jobId={jobId}
                zone={zone}
                onSuccess={(alts) => {
                  setAlternatives(alts);
                  setPhase('choose-plan');
                }}
              />
            )}

            {phase === 'choose-plan' && jobId && (
              <ChooseFloorPlan
                jobId={jobId}
                alternatives={alternatives}
                error={packageError}
                onGenerating={() => {
                  setPackageError(null);
                  setPhase('generating-package');
                }}
                onSuccess={(p) => {
                  setPkg(p);
                  setPhase('summary');
                }}
                onError={(msg) => {
                  setPackageError(msg);
                  setPhase('choose-plan');
                }}
              />
            )}

            {phase === 'summary' && pkg && (
              <DesignSummary
                pkg={pkg}
                onContinue={() =>
                  finish(toBuildingSchema(pkg.building_schema_json), 'c01', run.projectName || 'My House', pkg)
                }
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
