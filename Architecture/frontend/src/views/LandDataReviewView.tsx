import { useState, useMemo } from 'react'
import PlotPolygonPreview from '../components/PlotPolygonPreview'
import { triggerFloorPlanGeneration, pollFloorPlanStatus } from '../services/apiService'
import type { UserRequirements } from '../services/apiService'
import type { BuildableZone, CadastralData, FloorPlanAlternative } from '../types'

interface Props {
  jobId: string
  cadastral: CadastralData
  zone: BuildableZone
  onSuccess: (alternatives: FloorPlanAlternative[]) => void
}

// Minimum room sizes (sqm) — kept in sync by hand with
// Architecture/stages/stage3_floor_plan/prompt_builder.py's _MIN_ROOM_SQM,
// which is the single source of truth (generation and validation both read
// it directly; this file can't share that Python import, so update both when
// changing either). living_room/dining_room/bedroom/kitchen/master_bedroom
// come from Sri Lanka's UDA Planning & Building Regulations (Gazette 392/9,
// 1986); the rest are practical minimums, not a cited regulation — see the
// comment above _MIN_ROOM_SQM for details and confidence levels.
const ROOM_SQM_MIN: Record<string, number> = {
  living_room: 8.4, kitchen: 5.6, dining_room: 8.4,
  master_bedroom: 11.2, bedroom: 8.4, bathroom: 3.3,
  garage: 14, home_office: 5, prayer_room: 5,
  library: 5, maids_room: 5, kids_playroom: 8,
  gym: 12, home_theatre: 12, staircase: 4,
}

// Realistic maximum sizes — rooms shouldn't grow beyond these even on large plots
const ROOM_SQM_MAX: Record<string, number> = {
  living_room: 45, kitchen: 22, dining_room: 28,
  master_bedroom: 28, bedroom: 20, bathroom: 10,
  garage: 38, home_office: 18, prayer_room: 12,
  library: 22, maids_room: 14, kids_playroom: 22,
  gym: 35, home_theatre: 35, staircase: 4,
}

// Keep legacy alias for pill builds
const ROOM_SQM = ROOM_SQM_MIN

const ROOM_COLORS: Record<string, string> = {
  living_room: '#22c55e', kitchen: '#eab308', dining_room: '#fb923c',
  master_bedroom: '#6366f1', bedroom: '#8b5cf6', bathroom: '#0ea5e9',
  garage: '#64748b', home_office: '#14b8a6', prayer_room: '#f59e0b',
  library: '#a855f7', maids_room: '#6b7280', kids_playroom: '#ec4899',
  gym: '#ef4444', home_theatre: '#f97316', staircase: '#94a3b8',
}

type RoomItem = { key: string; label: string; sqm: number; color: string }

function buildRoomList(req: UserRequirements): RoomItem[] {
  const rooms: RoomItem[] = []
  if (req.living_room)  rooms.push({ key: 'living_room',    label: 'Living',      sqm: ROOM_SQM_MIN.living_room,    color: ROOM_COLORS.living_room })
  if (req.kitchen)      rooms.push({ key: 'kitchen',        label: 'Kitchen',     sqm: ROOM_SQM_MIN.kitchen,        color: ROOM_COLORS.kitchen })
  if (req.dining_room)  rooms.push({ key: 'dining_room',    label: 'Dining',      sqm: ROOM_SQM_MIN.dining_room,    color: ROOM_COLORS.dining_room })
  rooms.push({ key: 'master_bedroom', label: 'Master Bed', sqm: ROOM_SQM_MIN.master_bedroom, color: ROOM_COLORS.master_bedroom })
  for (let i = 1; i < req.bedrooms; i++)
    rooms.push({ key: 'bedroom', label: `Bed ${i + 1}`, sqm: ROOM_SQM_MIN.bedroom, color: ROOM_COLORS.bedroom })
  for (let i = 0; i < req.bathrooms; i++)
    rooms.push({ key: 'bathroom', label: `Bath ${i + 1}`, sqm: ROOM_SQM_MIN.bathroom, color: ROOM_COLORS.bathroom })
  if (req.garage) rooms.push({ key: 'garage', label: 'Garage', sqm: ROOM_SQM_MIN.garage, color: ROOM_COLORS.garage })
  for (const sr of req.special_rooms)
    rooms.push({ key: sr, label: sr.replace(/_/g, ' '), sqm: ROOM_SQM_MIN[sr] ?? 8, color: ROOM_COLORS[sr] ?? '#f43f5e' })
  // Not user-selectable — a real house with more than one floor needs a
  // staircase, so its space is always accounted for rather than left as a
  // silent gap between what this preview shows and what generation builds.
  if (req.floors >= 2)
    rooms.push({ key: 'staircase', label: 'Staircase', sqm: ROOM_SQM_MIN.staircase, color: ROOM_COLORS.staircase })
  return rooms
}

// Scale rooms proportionally to fill available budget, capped at realistic maximums
function scaleRooms(rooms: RoomItem[], availableSqm: number): RoomItem[] {
  const minTotal = rooms.reduce((s, r) => s + r.sqm, 0)
  if (minTotal <= 0 || availableSqm <= 0) return rooms
  const scale = Math.min(availableSqm / minTotal, 3.0) // cap at 3× minimum
  return rooms.map(r => ({
    ...r,
    sqm: Math.min(
      Math.round(r.sqm * scale * 2) / 2, // round to nearest 0.5
      ROOM_SQM_MAX[r.key] ?? r.sqm * 3
    )
  }))
}

function SpaceBudgetMeter({ req, zone }: { req: UserRequirements; zone: BuildableZone }) {
  const footprintSqm = (zone.buildable_area_sqm ?? zone.buildable_area_sqft / 10.764)
  const availableSqm = footprintSqm * req.floors

  const minRooms  = useMemo(() => buildRoomList(req), [req])
  // Over-budget check uses NBC minimums — if minimums don't fit, plan is impossible
  const minTotal  = minRooms.reduce((s, r) => s + r.sqm, 0)
  const overBudget = minTotal > availableSqm

  // Display uses recommended (scaled) sizes — fills available space realistically
  const rooms     = useMemo(() => scaleRooms(minRooms, availableSqm), [minRooms, availableSqm])
  const neededSqm = rooms.reduce((s, r) => s + r.sqm, 0)
  const pct       = Math.min((neededSqm / availableSqm) * 100, 120)
  const freeSqm   = availableSqm - neededSqm
  const displayPct = Math.min(pct, 100)

  const barGradient = pct < 60  ? 'from-emerald-400 to-emerald-500'
                    : pct < 85  ? 'from-amber-400 to-orange-400'
                    : pct < 100 ? 'from-orange-500 to-red-400'
                    :             'from-red-500 to-red-600'

  const pctColor = overBudget ? 'text-red-500' : pct > 85 ? 'text-orange-500' : 'text-emerald-500'

  const suggestion = overBudget
    ? (() => {
        const over = neededSqm - availableSqm
        const canAdd = req.floors < 3
        const removable = [...rooms].reverse().find(r => r.sqm >= over * 0.5)
        if (canAdd) return `Add 1 more floor to unlock ${footprintSqm.toFixed(0)} sqm extra.`
        if (removable) return `Remove "${removable.label}" to free ${removable.sqm} sqm.`
        return `Reduce bedrooms or remove special rooms to fit within budget.`
      })()
    : null

  return (
    <div className={`rounded-2xl border-2 p-5 shadow-sm transition-all duration-300 ${
      overBudget
        ? 'border-red-400 bg-red-50 dark:bg-red-950/20'
        : pct > 85
        ? 'border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-950/10'
        : 'border-emerald-200 dark:border-gray-700 bg-white dark:bg-gray-900'
    }`}>

      {/* Header row */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">
          Space Budget
        </span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {req.floors} floor{req.floors > 1 ? 's' : ''} × {footprintSqm.toFixed(0)} sqm
          </span>
          <span className={`text-3xl font-black tabular-nums leading-none transition-colors duration-300 ${pctColor}`}>
            {pct.toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Gradient progress bar */}
      <div className="relative h-4 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden mb-2">
        <div
          className={`absolute inset-y-0 left-0 rounded-full bg-gradient-to-r ${barGradient} transition-all duration-500 ease-out`}
          style={{ width: `${displayPct}%` }}
        />
        {overBudget && (
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-red-500/10 to-red-500/20 animate-pulse" />
        )}
      </div>

      {/* Segmented colour bar */}
      <div className="flex h-2 rounded-full overflow-hidden gap-px mb-4">
        {rooms.map((r, i) => (
          <div
            key={i}
            title={`${r.label}: ${r.sqm} sqm`}
            className="rounded-sm transition-all duration-300"
            style={{
              width: `${(r.sqm / Math.max(neededSqm, availableSqm)) * 100}%`,
              backgroundColor: r.color,
              minWidth: '3px',
            }}
          />
        ))}
        {!overBudget && (
          <div
            className="rounded-sm bg-gray-200 dark:bg-gray-700 flex-1"
            title={`Free: ${freeSqm.toFixed(0)} sqm`}
          />
        )}
      </div>

      {/* Room pills */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {rooms.map((r, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium transition-all duration-200"
            style={{
              backgroundColor: r.color + '22',
              color: r.color,
              border: `1px solid ${r.color}55`,
            }}
          >
            {r.label}
            <span className="opacity-70 font-normal">{r.sqm}m²</span>
          </span>
        ))}
      </div>

      {/* Stats row */}
      <div className="flex items-center justify-between text-xs border-t border-gray-100 dark:border-gray-800 pt-3">
        <div className="text-center">
          <div className="font-bold text-gray-900 dark:text-white text-sm">{neededSqm.toFixed(0)} m²</div>
          <div className="text-gray-400">needed</div>
        </div>
        <div className="w-px h-8 bg-gray-200 dark:bg-gray-700" />
        <div className="text-center">
          <div className="font-bold text-gray-900 dark:text-white text-sm">{availableSqm.toFixed(0)} m²</div>
          <div className="text-gray-400">available</div>
        </div>
        <div className="w-px h-8 bg-gray-200 dark:bg-gray-700" />
        <div className="text-center">
          <div className={`font-bold text-sm ${overBudget ? 'text-red-500' : 'text-emerald-500'}`}>
            {overBudget ? `+${(neededSqm - availableSqm).toFixed(0)} m²` : `${freeSqm.toFixed(0)} m²`}
          </div>
          <div className="text-gray-400">{overBudget ? 'over limit' : 'remaining'}</div>
        </div>
      </div>

      {/* Smart advice */}
      {overBudget && suggestion && (
        <div className="mt-3 flex items-start gap-2 p-3 bg-red-100 dark:bg-red-950/40 rounded-xl text-sm text-red-700 dark:text-red-300">
          <span className="text-base leading-none mt-0.5">⚠</span>
          <div>
            <span className="font-semibold">Over budget — </span>{suggestion}
          </div>
        </div>
      )}
      {!overBudget && pct > 85 && (
        <div className="mt-3 flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-950/20 rounded-xl text-sm text-amber-700 dark:text-amber-300">
          <span>⚡</span>
          <span>Almost full — only <strong>{freeSqm.toFixed(0)} m²</strong> remaining.</span>
        </div>
      )}
      {!overBudget && pct <= 75 && (
        <div className="mt-3 flex items-center gap-2 p-3 bg-emerald-50 dark:bg-emerald-950/20 rounded-xl text-sm text-emerald-700 dark:text-emerald-300">
          <span>✓</span>
          <span>Rooms scaled to fill your land. Sizes shown are <strong>recommended targets</strong> — add more rooms to use remaining <strong>{freeSqm.toFixed(0)} m²</strong>.</span>
        </div>
      )}
    </div>
  )
}

const ROAD_BADGE: Record<string, string> = {
  'main road':    'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  'lane':         'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  'private road': 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
}

const OUTDOOR_FEATURES = [
  { id: 'garden',          label: 'Garden' },
  { id: 'swimming_pool',   label: 'Swimming Pool' },
  { id: 'patio',           label: 'Patio' },
  { id: 'rooftop_terrace', label: 'Rooftop Terrace' },
  { id: 'balcony',         label: 'Balcony' },
  { id: 'outdoor_kitchen', label: 'Outdoor Kitchen' },
]

const SPECIAL_ROOMS = [
  { id: 'home_office',   label: 'Home Office' },
  { id: 'home_theatre',  label: 'Home Theatre' },
  { id: 'gym',           label: 'Gym' },
  { id: 'prayer_room',   label: 'Prayer Room' },
  { id: 'maids_room',    label: 'Maid\'s Room' },
  { id: 'library',       label: 'Library' },
  { id: 'kids_playroom', label: 'Kids Playroom' },
]

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm">
      <h3 className="font-semibold text-gray-900 dark:text-white mb-4 pb-3 border-b border-gray-100 dark:border-gray-800">
        {title}
      </h3>
      {children}
    </div>
  )
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">
      <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-900 dark:text-white text-right max-w-[60%]">{value}</span>
    </div>
  )
}

function StepLabel({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className="w-6 h-6 rounded-full bg-orange-500 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">{n}</span>
      <span className="font-semibold text-gray-900 dark:text-white">{label}</span>
    </div>
  )
}

function SelectField({ label, value, onChange, children }: {
  label: string; value: string | number
  onChange: (v: string) => void; children: React.ReactNode
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
      >
        {children}
      </select>
    </div>
  )
}

function CheckGroup({ items, selected, onChange }: {
  items: { id: string; label: string }[]
  selected: string[]
  onChange: (id: string, checked: boolean) => void
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {items.map(item => {
        const checked = selected.includes(item.id)
        return (
          <label
            key={item.id}
            className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors select-none text-sm
              ${checked
                ? 'border-orange-400 bg-orange-50 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300'
                : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={e => onChange(item.id, e.target.checked)}
              className="w-4 h-4 rounded accent-orange-500 flex-shrink-0"
            />
            {item.label}
          </label>
        )
      })}
    </div>
  )
}

function toggle(list: string[], id: string, checked: boolean): string[] {
  return checked ? [...list, id] : list.filter(x => x !== id)
}

export default function LandDataReviewView({ jobId, cadastral, zone, onSuccess }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollMsg, setPollMsg] = useState('')

  const maxFloors = 4 // NBC Sri Lanka limits floors by road width & zone type, not land area
  const gps = cadastral.gps_coordinates[0]

  const [req, setReq] = useState<UserRequirements>({
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
  })

  const overBudget = useMemo(() => {
    const footprintSqm = zone.buildable_area_sqm ?? zone.buildable_area_sqft / 10.764
    const available = footprintSqm * req.floors
    const needed = buildRoomList(req).reduce((s, r) => s + r.sqm, 0)
    return needed > available
  }, [req, zone])

  const generate = async () => {
    setLoading(true)
    setError(null)
    try {
      await triggerFloorPlanGeneration(jobId, req)
      setPollMsg('Generating floor plans… this takes 60–120 seconds.')

      const poll = async (): Promise<FloorPlanAlternative[]> => {
        await new Promise(r => setTimeout(r, 3000))
        const res = await pollFloorPlanStatus(jobId)
        if (res.status === 'complete' && res.alternatives) return res.alternatives
        if (res.status === 'failed') throw new Error('Floor plan generation failed.')
        setPollMsg(`Still generating (${res.status})…`)
        return poll()
      }

      const alternatives = await poll()
      onSuccess(alternatives)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-10 space-y-8">

      {/* Step 1 — Extracted land data */}
      <div>
        <StepLabel n={1} label="Extracted Land Data" />
        <div className="grid md:grid-cols-2 gap-5">
          <SectionCard title="Site Information">
            <DataRow label="District" value={cadastral.district} />
            <DataRow label="Land Area" value={`${cadastral.land_area_perches.toFixed(2)} perches (${cadastral.land_area_sqft.toFixed(0)} sqft)`} />
            <div className="flex justify-between py-2 border-b border-gray-100 dark:border-gray-800">
              <span className="text-sm text-gray-500 dark:text-gray-400">Road Access</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ROAD_BADGE[cadastral.road_access_type] ?? 'bg-gray-100 text-gray-700'}`}>
                {cadastral.road_access_type}
              </span>
            </div>
            {gps && <DataRow label="GPS Coordinates" value={`${gps[0].toFixed(6)}, ${gps[1].toFixed(6)}`} />}
            <DataRow label="Orientation" value={cadastral.orientation} />
          </SectionCard>

          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm flex flex-col">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-3 pb-3 border-b border-gray-100 dark:border-gray-800">
              Plot Visualisation
            </h3>
            <div className="flex-1 flex items-center justify-center">
              <PlotPolygonPreview
                plotPolygon={cadastral.plot_boundary_polygon}
                buildablePolygon={zone.buildable_polygon}
                size={240}
              />
            </div>
          </div>
        </div>

        {/* Regulatory summary */}
        <div className="mt-5 bg-orange-50 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-800 rounded-2xl p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3 text-sm uppercase tracking-wide">
            NBC Sri Lanka — Regulatory Summary
          </h3>
          <div className="grid sm:grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-xl font-bold text-orange-500">{zone.buildable_area_sqft.toFixed(0)}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">sqft buildable</div>
            </div>
            <div>
              <div className="text-xl font-bold text-orange-500">{(zone.bcr_value * 100).toFixed(0)}%</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Coverage (BCR)</div>
            </div>
            <div>
              <div className="text-xl font-bold text-orange-500">{zone.front_setback_ft.toFixed(1)} ft</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">Front setback</div>
            </div>
          </div>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">{zone.constraints_summary}</p>
        </div>
      </div>

      {/* Step 2 — Design requirements */}
      <div>
        <StepLabel n={2} label="Design Your Dream Home" />
        <div className="space-y-5">

          {/* Core Specifications */}
          <SectionCard title="Core Specifications">
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <SelectField label="Bedrooms" value={req.bedrooms} onChange={v => setReq(r => ({ ...r, bedrooms: Number(v) }))}>
                {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n} bedroom{n > 1 ? 's' : ''}</option>)}
              </SelectField>

              <SelectField label="Bathrooms" value={req.bathrooms} onChange={v => setReq(r => ({ ...r, bathrooms: Number(v) }))}>
                {[1, 2, 3, 4].map(n => <option key={n} value={n}>{n} bathroom{n > 1 ? 's' : ''}</option>)}
              </SelectField>

              <SelectField
                label={`Floors (NBC max: ${maxFloors})`}
                value={req.floors}
                onChange={v => setReq(r => ({ ...r, floors: Number(v) }))}
              >
                {Array.from({ length: maxFloors }, (_, i) => i + 1).map(n => (
                  <option key={n} value={n}>{n} floor{n > 1 ? 's' : ''}</option>
                ))}
              </SelectField>

              <SelectField label="Architectural Style" value={req.style} onChange={v => setReq(r => ({ ...r, style: v as UserRequirements['style'] }))}>
                <option value="modern">Modern</option>
                <option value="contemporary">Contemporary</option>
                <option value="traditional">Traditional</option>
                <option value="minimalist">Minimalist</option>
                <option value="colonial">Colonial</option>
              </SelectField>

              {/* Standard rooms always-on toggle */}
              <div className="sm:col-span-2 flex flex-wrap gap-3 items-end">
                {([
                  ['dining_room', 'Dining Room'],
                  ['garage',      'Garage'],
                ] as [keyof UserRequirements, string][]).map(([key, label]) => {
                  const checked = req[key] as boolean
                  return (
                    <label
                      key={key}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer text-sm transition-colors
                        ${checked
                          ? 'border-orange-400 bg-orange-50 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300'
                          : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                        }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={e => setReq(r => ({ ...r, [key]: e.target.checked }))}
                        className="w-4 h-4 rounded accent-orange-500"
                      />
                      {label}
                    </label>
                  )
                })}
              </div>
            </div>
          </SectionCard>

          {/* Live Space Budget Meter */}
          <SpaceBudgetMeter req={req} zone={zone} />

          {/* Outdoor Features */}
          <SectionCard title="Outdoor Features">
            <CheckGroup
              items={OUTDOOR_FEATURES}
              selected={req.outdoor_features}
              onChange={(id, checked) => setReq(r => ({ ...r, outdoor_features: toggle(r.outdoor_features, id, checked) }))}
            />
          </SectionCard>

          {/* Special Rooms */}
          <SectionCard title="Special Rooms">
            <CheckGroup
              items={SPECIAL_ROOMS}
              selected={req.special_rooms}
              onChange={(id, checked) => setReq(r => ({ ...r, special_rooms: toggle(r.special_rooms, id, checked) }))}
            />
          </SectionCard>

          {/* Additional Notes */}
          <SectionCard title="Additional Details">
            <textarea
              value={req.additional_notes}
              onChange={e => setReq(r => ({ ...r, additional_notes: e.target.value }))}
              rows={4}
              placeholder="Anything else? e.g. specific materials, vastu alignment, split-level layout, double-height living room, specific room adjacencies…"
              className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none placeholder:text-gray-400 dark:placeholder:text-gray-600"
            />
          </SectionCard>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}
      {loading && pollMsg && (
        <p className="text-sm text-orange-600 dark:text-orange-400 text-center animate-pulse">{pollMsg}</p>
      )}

      <div className="space-y-2">
        {overBudget && !loading && (
          <p className="text-center text-sm text-red-500 font-medium animate-pulse">
            Reduce rooms or add a floor before generating
          </p>
        )}
        <button
          onClick={generate}
          disabled={loading || overBudget}
          className="w-full py-3.5 px-6 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 text-base"
        >
          {loading ? (
            <>
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Generating Floor Plans…
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {overBudget ? 'Over Budget — Adjust Rooms First' : 'Generate Floor Plan Options'}
            </>
          )}
        </button>
      </div>
    </div>
  )
}
