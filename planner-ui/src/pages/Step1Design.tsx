import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Stat } from '../components/ui';
import type { BuildingSchema, RunState } from '../types';

/* Step 1 stands in for Component 01 (Architecture), which is not wired up yet.
 * C01's only downstream output is a BuildingSchema, so producing one by hand is
 * a complete substitute — nothing after this step can tell the difference.
 * When C01 is ready, replace this form with:
 *   POST /process-cadastral → POST /generate-floorplans → poll
 *   GET /floorplans/status/{id} → POST /select-plan
 * and take FullDesignPackage.building_schema_json. */

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

const DISTRICTS = [
  'Ampara', 'Anuradhapura', 'Badulla', 'Batticaloa', 'Colombo', 'Galle', 'Gampaha',
  'Hambantota', 'Jaffna', 'Kalutara', 'Kandy', 'Kegalle', 'Kilinochchi', 'Kurunegala',
  'Mannar', 'Matale', 'Matara', 'Monaragala', 'Mullaitivu', 'Nuwara Eliya',
  'Polonnaruwa', 'Puttalam', 'Ratnapura', 'Trincomalee', 'Vavuniya',
];

/* C04's delay model encodes province WITH the " Province" suffix, so these
 * strings must match exactly or /progress/predict returns a 500. */
const PROVINCES = [
  'Western Province', 'Central Province', 'Southern Province', 'Northern Province',
  'Eastern Province', 'North Western Province', 'North Central Province',
  'Uva Province', 'Sabaragamuwa Province',
];

/* The delay-prediction model was trained on a subset only — anything outside
 * these lists reaches step 4 fine but cannot be scored. Read straight out of
 * performance/models/label_encoders.pkl. */
const C04_DISTRICTS = new Set([
  'Ampara', 'Batticaloa', 'Colombo', 'Galle', 'Gampaha', 'Hambantota', 'Jaffna',
  'Kalutara', 'Kilinochchi', 'Mannar', 'Matara', 'Mullaitivu', 'Trincomalee', 'Vavuniya',
]);
const C04_PROVINCES = new Set([
  'Eastern Province', 'Northern Province', 'Southern Province', 'Western Province',
]);

type Props = { run: RunState; update: (p: Partial<RunState>) => void };

export function Step1Design({ run, update }: Props) {
  const nav = useNavigate();
  const [name, setName] = useState(run.projectName);
  const [s, setS] = useState<BuildingSchema>(run.step1?.buildingSchema ?? SAMPLE);

  const set = <K extends keyof BuildingSchema>(k: K, v: BuildingSchema[K]) =>
    setS((prev) => ({ ...prev, [k]: v }));

  const numField = (
    label: string,
    key: keyof BuildingSchema,
    step = 1,
    hint?: string,
  ) => (
    <label className="field">
      {label}
      {hint && <span className="faint">{hint}</span>}
      <input
        type="number"
        step={step}
        min={0}
        value={String(s[key] ?? '')}
        onChange={(e) => set(key, Number(e.target.value) as never)}
      />
    </label>
  );

  const roomsTotal = Object.values(s.rooms).reduce((a, b) => a + b, 0);

  const submit = () => {
    update({
      projectName: name.trim() || 'My House',
      step1: { buildingSchema: s, source: 'stub' },
      // A changed design invalidates everything computed from it.
      step2: undefined,
      step3: undefined,
      step4: undefined,
    });
    nav('/step/2');
  };

  return (
    <div className="stack">
      <div className="between">
        <div>
          <h1>Design</h1>
          <p className="muted">
            Describe the building. This is the schema Cost Estimation prices in step 2.
          </p>
        </div>
        <button onClick={() => setS(SAMPLE)}>Load sample</button>
      </div>

      <div className="alert info">
        <span className="title">Component 01 is not connected yet.</span> This form stands in
        for it. Everything downstream — cost, timeline, performance — is real.
      </div>

      <Card title="Project">
        <label className="field">
          Project name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="My House" />
        </label>
      </Card>

      <Card title="Geometry">
        <div className="grid cols-3">
          {numField('Footprint (m²)', 'footprint_sqm', 1)}
          {numField('Perimeter (m)', 'perimeter', 0.1)}
          {numField('Floors', 'floors', 1)}
          {numField('Floor height (m)', 'floor_height', 0.1)}
          {numField('Wall height (m)', 'wall_height', 0.1)}
          {numField('Excavation depth (m)', 'excavation_depth', 0.1)}
        </div>
      </Card>

      <Card title="Structure & openings">
        <div className="grid cols-3">
          {numField('Column count', 'column_count', 1, '0 = auto-derive')}
          {numField('Openings (m²)', 'openings_sqm', 1, 'doors + windows')}
          {numField('Internal wall length (m)', 'internal_wall_length', 0.5)}
        </div>
      </Card>

      <Card title="Finish">
        <div className="grid cols-2">
          <label className="field">
            Finish grade
            <select
              value={s.finish_grade}
              onChange={(e) => set('finish_grade', e.target.value as BuildingSchema['finish_grade'])}
            >
              <option value="economy">Economy</option>
              <option value="mid">Mid</option>
              <option value="luxury">Luxury</option>
            </select>
          </label>
          <label className="field">
            Roof type
            <select
              value={s.roof_type}
              onChange={(e) => set('roof_type', e.target.value as BuildingSchema['roof_type'])}
            >
              <option value="flat">Flat</option>
              <option value="gable">Gable</option>
              <option value="hip">Hip</option>
              <option value="mansard">Mansard</option>
            </select>
          </label>
        </div>
      </Card>

      <Card title="Site" subtitle="District and province travel all the way to Performance">
        {(!C04_DISTRICTS.has(s.district ?? '') || !C04_PROVINCES.has(s.province ?? '')) && (
          <div className="alert warn" style={{ marginBottom: '1rem' }}>
            <span className="title">Delay prediction unavailable for this location.</span>{' '}
            Performance's model was trained on {C04_DISTRICTS.size} districts and{' '}
            {C04_PROVINCES.size} provinces only. Cost and timeline work everywhere; step 4's
            delay prediction will error unless you pick a supported district <em>and</em>{' '}
            province (e.g. Galle / Southern Province).
          </div>
        )}
        <div className="grid cols-3">
          <label className="field">
            District
            <select value={s.district ?? ''} onChange={(e) => set('district', e.target.value)}>
              {DISTRICTS.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Province
            <select value={s.province ?? ''} onChange={(e) => set('province', e.target.value)}>
              {PROVINCES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          {numField('Plot area (m²)', 'plot_area', 1)}
          <label className="field">
            Terrain
            <select
              value={s.terrain}
              onChange={(e) => set('terrain', e.target.value as BuildingSchema['terrain'])}
            >
              <option value="flat">Flat</option>
              <option value="sloped">Sloped</option>
              <option value="hilly">Hilly</option>
              <option value="rocky">Rocky</option>
            </select>
          </label>
          <label className="field">
            Road access
            <select
              value={s.road_access}
              onChange={(e) => set('road_access', e.target.value as BuildingSchema['road_access'])}
            >
              <option value="paved">Paved</option>
              <option value="gravel">Gravel</option>
              <option value="track">Track</option>
              <option value="none">None</option>
            </select>
          </label>
          <label className="field">
            Coastal site
            <select
              value={s.is_coastal ? 'yes' : 'no'}
              onChange={(e) => set('is_coastal', e.target.value === 'yes')}
            >
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </label>
        </div>
      </Card>

      <Card title="Rooms" subtitle={`${roomsTotal} rooms defined`}>
        <div className="grid cols-4">
          {(['bedroom', 'bathroom', 'living_room', 'kitchen'] as const).map((rk) => (
            <label className="field" key={rk}>
              {rk.replace('_', ' ')}
              <input
                type="number"
                min={0}
                value={s.rooms[rk] ?? 0}
                onChange={(e) =>
                  set('rooms', { ...s.rooms, [rk]: Number(e.target.value) })
                }
              />
            </label>
          ))}
          {numField('Bathroom count', 'bathroom_count', 1)}
          {numField('Room count', 'room_count', 1)}
        </div>
      </Card>

      <Card title="Cost indexing dates">
        <div className="grid cols-2">
          <label className="field">
            Base rate date
            <input
              type="date"
              value={s.base_rate_date}
              onChange={(e) => set('base_rate_date', e.target.value)}
            />
          </label>
          <label className="field">
            Target date
            <span className="faint">when construction is expected to run</span>
            <input
              type="date"
              value={s.target_date ?? ''}
              onChange={(e) => set('target_date', e.target.value)}
            />
          </label>
        </div>
      </Card>

      <div className="grid cols-4">
        <Stat label="Floor area" value={`${(s.footprint_sqm * s.floors).toFixed(0)} m²`} />
        <Stat label="Floors" value={s.floors} />
        <Stat label="Finish" value={s.finish_grade} />
        <Stat label="District" value={s.district ?? '—'} />
      </div>

      <div className="footer-nav">
        <span />
        <button className="primary" onClick={submit} disabled={s.footprint_sqm <= 0}>
          Move to Estimation →
        </button>
      </div>
    </div>
  );
}
