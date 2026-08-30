import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { BuildingSchema, C01BuildableZone, C01CadastralData, C01FloorPlanAlternative, C01FullDesignPackage, RunState } from '../types';
import { toBuildingSchema } from '../api/services';
import { UploadCadastral } from './step1/UploadCadastral';
import { DesignRequirements } from './step1/DesignRequirements';
import { ChooseFloorPlan } from './step1/ChooseFloorPlan';
import { GeneratingPackage } from './step1/GeneratingPackage';
import { DesignSummary } from './step1/DesignSummary';

/* Component 01 (Architecture) is now wired up for real:
 *   POST /process-cadastral → POST /generate-floorplans → poll
 *   GET /floorplans/status/{id} → POST /select-plan
 * FullDesignPackage.building_schema_json maps onto BuildingSchema via
 * toBuildingSchema() in api/services.ts — nothing downstream of step 1
 * changes regardless of which path produced the schema.
 *
 * "Load sample" below is kept as a secondary escape hatch for offline
 * dev/demo use (no C01 backend running) — the real flow is the default. */

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

  return (
    <div className="stack">
      {phase === 'upload' && (
        <>
          <UploadCadastral
            onSuccess={(res) => {
              setJobId(res.job_id);
              setCadastral(res.cadastral_data);
              setZone(res.buildable_zone);
              setPhase('requirements');
            }}
          />
          <div className="alert info">
            <span className="title">No cadastral plan handy?</span>{' '}
            <button className="ghost" onClick={loadSample}>
              Skip with sample data →
            </button>
          </div>
        </>
      )}

      {phase === 'requirements' && jobId && cadastral && zone && (
        <DesignRequirements
          jobId={jobId}
          cadastral={cadastral}
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

      {phase === 'generating-package' && <GeneratingPackage />}

      {phase === 'summary' && pkg && (
        <DesignSummary
          pkg={pkg}
          onContinue={() =>
            finish(toBuildingSchema(pkg.building_schema_json), 'c01', run.projectName || 'My House', pkg)
          }
        />
      )}
    </div>
  );
}
