import { useMemo, useState } from 'react';
import { Card, Stat, Bar } from '../../components/ui';
import { ApiError } from '../../api/client';
import {
  triggerFloorPlanGeneration,
  pollFloorPlanStatus,
} from '../../api/services';
import type {
  C01BuildableZone,
  C01CadastralData,
  C01FloorPlanAlternative,
  C01UserRequirements,
} from '../../types';

/* Minimum room sizes (sqm) — kept in sync by hand with Architecture's
 * stages/stage3_floor_plan/prompt_builder.py _MIN_ROOM_SQM, the single
 * source of truth generation and validation both read directly. This file
 * can't share that Python import, so update both when changing either.
 * living_room/dining_room/bedroom/kitchen/master_bedroom come from Sri
 * Lanka's UDA Planning & Building Regulations (Gazette 392/9, 1986); the
 * rest are practical minimums, not a cited regulation. */
const ROOM_SQM_MIN: Record<string, number> = {
  living_room: 8.4, kitchen: 5.6, dining_room: 8.4,
  master_bedroom: 11.2, bedroom: 8.4, bathroom: 3.3,
  garage: 14, home_office: 5, prayer_room: 5,
  library: 5, maids_room: 5, kids_playroom: 8,
  gym: 12, home_theatre: 12, staircase: 4,
};

const OUTDOOR_FEATURES = [
  { id: 'garden', label: 'Garden' },
  { id: 'swimming_pool', label: 'Swimming Pool' },
  { id: 'patio', label: 'Patio' },
  { id: 'rooftop_terrace', label: 'Rooftop Terrace' },
  { id: 'balcony', label: 'Balcony' },
  { id: 'outdoor_kitchen', label: 'Outdoor Kitchen' },
];

const SPECIAL_ROOMS = [
  { id: 'home_office', label: 'Home Office' },
  { id: 'home_theatre', label: 'Home Theatre' },
  { id: 'gym', label: 'Gym' },
  { id: 'prayer_room', label: 'Prayer Room' },
  { id: 'maids_room', label: "Maid's Room" },
  { id: 'library', label: 'Library' },
  { id: 'kids_playroom', label: 'Kids Playroom' },
];

function toggle(list: string[], id: string, checked: boolean): string[] {
  return checked ? [...list, id] : list.filter((x) => x !== id);
}

function roomList(req: C01UserRequirements): { label: string; sqm: number }[] {
  const rooms: { label: string; sqm: number }[] = [];
  if (req.living_room) rooms.push({ label: 'Living', sqm: ROOM_SQM_MIN.living_room });
  if (req.kitchen) rooms.push({ label: 'Kitchen', sqm: ROOM_SQM_MIN.kitchen });
  if (req.dining_room) rooms.push({ label: 'Dining', sqm: ROOM_SQM_MIN.dining_room });
  rooms.push({ label: 'Master Bed', sqm: ROOM_SQM_MIN.master_bedroom });
  for (let i = 1; i < req.bedrooms; i++) rooms.push({ label: `Bed ${i + 1}`, sqm: ROOM_SQM_MIN.bedroom });
  for (let i = 0; i < req.bathrooms; i++) rooms.push({ label: `Bath ${i + 1}`, sqm: ROOM_SQM_MIN.bathroom });
  if (req.garage) rooms.push({ label: 'Garage', sqm: ROOM_SQM_MIN.garage });
  for (const sr of req.special_rooms) rooms.push({ label: sr.replace(/_/g, ' '), sqm: ROOM_SQM_MIN[sr] ?? 8 });
  if (req.floors >= 2) rooms.push({ label: 'Staircase', sqm: ROOM_SQM_MIN.staircase });
  return rooms;
}

const ROAD_TONE: Record<string, 'ok' | 'warn' | 'neutral'> = {
  'main road': 'ok',
  lane: 'warn',
  'private road': 'neutral',
};

type Props = {
  jobId: string;
  cadastral: C01CadastralData;
  zone: C01BuildableZone;
  onSuccess: (alternatives: C01FloorPlanAlternative[]) => void;
};

// This deliberately does NOT switch to a separate top-level "generating"
// view while polling — it shows its own inline loading/error state instead
// (matching Architecture/frontend's LandDataReviewView.tsx). Only the later
// Stage 5 package-generation step gets a dedicated full-page view, since
// unmounting this component mid-poll would lose its own error message.
export function DesignRequirements({ jobId, cadastral, zone, onSuccess }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollMsg, setPollMsg] = useState('');

  const maxFloors = 4; // NBC Sri Lanka limits floors by road width & zone type, not land area
  const gps = cadastral.gps_coordinates[0];

  const [req, setReq] = useState<C01UserRequirements>({
    bedrooms: 3,
    bathrooms: 2,
    living_room: true,
    kitchen: true,
    dining_room: true,
    garage: false,
    style: 'modern',
    floors: 1,
    outdoor_features: [],
    special_rooms: [],
    additional_notes: '',
  });

  const footprintSqm = zone.buildable_area_sqm ?? zone.buildable_area_sqft / 10.764;
  const availableSqm = footprintSqm * req.floors;
  const rooms = useMemo(() => roomList(req), [req]);
  const neededSqm = rooms.reduce((s, r) => s + r.sqm, 0);
  const overBudget = neededSqm > availableSqm;
  const usagePct = availableSqm > 0 ? (neededSqm / availableSqm) * 100 : 0;

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      await triggerFloorPlanGeneration(jobId, req);
      setPollMsg('Generating floor plans… this takes 60–120 seconds.');

      const poll = async (): Promise<C01FloorPlanAlternative[]> => {
        await new Promise((r) => setTimeout(r, 3000));
        const res = await pollFloorPlanStatus(jobId);
        if (res.status === 'complete' && res.alternatives) return res.alternatives;
        if (res.status === 'failed') throw new Error(res.error ?? 'Floor plan generation failed.');
        setPollMsg(`Still generating (${res.status})…`);
        return poll();
      };

      const alternatives = await poll();
      onSuccess(alternatives);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Generation failed.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <div>
        <h1>Design</h1>
        <p className="muted">Extracted from your plan, plus what you want built on it.</p>
      </div>

      <Card title="Extracted Land Data">
        <div className="grid cols-4" style={{ marginBottom: '1rem' }}>
          <Stat label="District" value={cadastral.district} />
          <Stat
            label="Land area"
            value={`${cadastral.land_area_perches.toFixed(2)} P`}
            hint={`${cadastral.land_area_sqft.toFixed(0)} sqft`}
          />
          <Stat
            label="Road access"
            value={<span className={`badge ${ROAD_TONE[cadastral.road_access_type] ?? 'neutral'}`}>{cadastral.road_access_type}</span>}
          />
          <Stat label="Orientation" value={cadastral.orientation} />
        </div>
        {gps && (
          <p className="faint">
            GPS: {gps[0].toFixed(6)}, {gps[1].toFixed(6)}
          </p>
        )}
        <div className="alert info">
          <span className="title">NBC Sri Lanka regulatory summary.</span> {zone.buildable_area_sqft.toFixed(0)} sqft
          buildable, {(zone.bcr_value * 100).toFixed(0)}% max coverage, {zone.front_setback_ft.toFixed(1)} ft front
          setback.
          <br />
          {zone.constraints_summary}
        </div>
      </Card>

      <Card title="Design Your Dream Home">
        <div className="grid cols-3" style={{ marginBottom: '1rem' }}>
          <label className="field">
            Bedrooms
            <select value={req.bedrooms} onChange={(e) => setReq((r) => ({ ...r, bedrooms: Number(e.target.value) }))}>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n} bedroom{n > 1 ? 's' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Bathrooms
            <select value={req.bathrooms} onChange={(e) => setReq((r) => ({ ...r, bathrooms: Number(e.target.value) }))}>
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n} bathroom{n > 1 ? 's' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Floors (NBC max: {maxFloors})
            <select value={req.floors} onChange={(e) => setReq((r) => ({ ...r, floors: Number(e.target.value) }))}>
              {Array.from({ length: maxFloors }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n} floor{n > 1 ? 's' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Architectural style
            <select
              value={req.style}
              onChange={(e) => setReq((r) => ({ ...r, style: e.target.value as C01UserRequirements['style'] }))}
            >
              <option value="modern">Modern</option>
              <option value="contemporary">Contemporary</option>
              <option value="traditional">Traditional</option>
              <option value="minimalist">Minimalist</option>
              <option value="colonial">Colonial</option>
            </select>
          </label>
          {(['dining_room', 'garage'] as const).map((key) => (
            <label key={key} className={`tile${req[key] ? ' checked' : ''}`}>
              <input
                type="checkbox"
                checked={req[key]}
                onChange={(e) => setReq((r) => ({ ...r, [key]: e.target.checked }))}
              />
              {key === 'dining_room' ? 'Dining Room' : 'Garage'}
            </label>
          ))}
        </div>

        <div className="between" style={{ marginBottom: '0.4rem' }}>
          <span className="faint">
            Space budget — {req.floors} floor{req.floors > 1 ? 's' : ''} × {footprintSqm.toFixed(0)} m²
          </span>
          <strong className={overBudget ? 'mono' : 'mono'} style={{ color: overBudget ? 'var(--danger)' : 'var(--ok)' }}>
            {usagePct.toFixed(0)}%
          </strong>
        </div>
        <Bar value={neededSqm} max={availableSqm} />
        <div className="room-pill-row" style={{ marginTop: '0.6rem', marginBottom: '0.4rem' }}>
          {rooms.map((r, i) => (
            <span key={i} className="room-pill">
              {r.label} {r.sqm}m²
            </span>
          ))}
        </div>
        {overBudget ? (
          <div className="alert error">
            Needs {neededSqm.toFixed(0)} m² but only {availableSqm.toFixed(0)} m² available — reduce rooms or add a
            floor before generating.
          </div>
        ) : (
          <p className="faint">
            {neededSqm.toFixed(0)} m² needed of {availableSqm.toFixed(0)} m² available (
            {(availableSqm - neededSqm).toFixed(0)} m² remaining).
          </p>
        )}
      </Card>

      <Card title="Outdoor Features">
        <div className="tile-grid">
          {OUTDOOR_FEATURES.map((f) => {
            const checked = req.outdoor_features.includes(f.id);
            return (
              <label key={f.id} className={`tile${checked ? ' checked' : ''}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => setReq((r) => ({ ...r, outdoor_features: toggle(r.outdoor_features, f.id, e.target.checked) }))}
                />
                {f.label}
              </label>
            );
          })}
        </div>
      </Card>

      <Card title="Special Rooms">
        <div className="tile-grid">
          {SPECIAL_ROOMS.map((f) => {
            const checked = req.special_rooms.includes(f.id);
            return (
              <label key={f.id} className={`tile${checked ? ' checked' : ''}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => setReq((r) => ({ ...r, special_rooms: toggle(r.special_rooms, f.id, e.target.checked) }))}
                />
                {f.label}
              </label>
            );
          })}
        </div>
      </Card>

      <Card title="Additional Details">
        <textarea
          value={req.additional_notes}
          onChange={(e) => setReq((r) => ({ ...r, additional_notes: e.target.value }))}
          rows={3}
          placeholder="Anything else? e.g. specific materials, vastu alignment, split-level layout…"
        />
      </Card>

      {error && <div className="alert error">{error}</div>}
      {loading && pollMsg && <p className="faint">{pollMsg}</p>}

      <div className="footer-nav">
        <span />
        <button className="primary" onClick={generate} disabled={loading || overBudget}>
          {loading ? (
            <>
              <span className="spinner" aria-hidden /> Generating…
            </>
          ) : overBudget ? (
            'Over budget — adjust rooms first'
          ) : (
            'Generate Floor Plan Options'
          )}
        </button>
      </div>
    </div>
  );
}
