import { useState } from 'react'
import type { FloorPlanAlternative, Room } from '../types'
import ScoreBar from './ScoreBar'

interface FloorPlanCardProps {
  alternative: FloorPlanAlternative
  isSelected: boolean
  onSelect: () => void
}

const VARIANT_COLORS = {
  conservative: 'border-blue-500 ring-blue-200 dark:ring-blue-800',
  balanced:     'border-green-500 ring-green-200 dark:ring-green-800',
  creative:     'border-orange-500 ring-orange-200 dark:ring-orange-800',
}

const TEMP_BADGE = {
  conservative: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  balanced:     'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  creative:     'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
}

// Colour per room type for the mini layout
function roomColor(name: string): { fill: string; stroke: string } {
  const n = name.toLowerCase()
  if (n.includes('master') || n.includes('bedroom'))
    return { fill: 'rgba(99,102,241,0.18)', stroke: '#6366f1' }
  if (n.includes('living'))
    return { fill: 'rgba(34,197,94,0.18)', stroke: '#22c55e' }
  if (n.includes('kitchen'))
    return { fill: 'rgba(234,179,8,0.22)', stroke: '#eab308' }
  if (n.includes('dining'))
    return { fill: 'rgba(251,146,60,0.22)', stroke: '#fb923c' }
  if (n.includes('bath') || n.includes('toilet'))
    return { fill: 'rgba(14,165,233,0.18)', stroke: '#0ea5e9' }
  if (n.includes('garage'))
    return { fill: 'rgba(100,116,139,0.18)', stroke: '#64748b' }
  if (n.includes('verandah') || n.includes('veranda') || n.includes('porch'))
    return { fill: 'rgba(168,162,158,0.18)', stroke: '#a8a29e' }
  return { fill: 'rgba(249,115,22,0.12)', stroke: '#f97316' }
}

function MiniRoomLayout({ alternative }: { alternative: FloorPlanAlternative }) {
  const SIZE = 220
  const PAD = 10
  const inner = SIZE - PAD * 2

  const allFloors = [...new Set(alternative.rooms.map((r: Room) => r.floor ?? 1))].sort()
  const [activeFloor, setActiveFloor] = useState(allFloors[0] ?? 1)
  const multiFloor = allFloors.length > 1

  const rooms = alternative.rooms.filter((r: Room) => (r.floor ?? 1) === activeFloor)
  if (!alternative.rooms.length) return null

  // Find the bounding box of all room rectangles (positions + sizes).
  // position_x/y and width_ft/length_ft now share the same coordinate system
  // so non-overlapping rooms in the solver remain non-overlapping here.
  const allX = rooms.flatMap((r: Room) => [r.position_x, r.position_x + r.width_ft])
  const allY = rooms.flatMap((r: Room) => [r.position_y, r.position_y + r.length_ft])
  const minX = Math.min(...allX)
  const maxX = Math.max(...allX)
  const minY = Math.min(...allY)
  const maxY = Math.max(...allY)
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1

  // Maintain aspect ratio so plan doesn't appear squished
  const plotAspect = rangeX / rangeY
  let drawW = inner
  let drawH = inner
  if (plotAspect > 1) {
    drawH = inner / plotAspect
  } else {
    drawW = inner * plotAspect
  }
  const offX = PAD + (inner - drawW) / 2
  const offY = PAD + (inner - drawH) / 2

  const toSvgX = (v: number) => offX + ((v - minX) / rangeX) * drawW
  const toSvgY = (v: number) => offY + ((v - minY) / rangeY) * drawH
  const toSvgW = (v: number) => (v / rangeX) * drawW
  const toSvgH = (v: number) => (v / rangeY) * drawH

  return (
    <div>
      {multiFloor && (
        <div className="flex gap-1 mb-1">
          {allFloors.map(f => (
            <button
              key={f}
              onClick={e => { e.stopPropagation(); setActiveFloor(f) }}
              className={`text-[10px] px-2 py-0.5 rounded font-medium transition-colors ${
                activeFloor === f
                  ? 'bg-orange-500 text-white'
                  : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
            >
              Floor {f}
            </button>
          ))}
        </div>
      )}
    <svg
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="w-full rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
    >
      {/* plot boundary outline */}
      <rect
        x={offX} y={offY} width={drawW} height={drawH}
        fill="none"
        stroke="#d1d5db"
        strokeWidth="1"
        strokeDasharray="4 2"
        rx="1"
      />

      {rooms.map((r: Room, i: number) => {
        const x = toSvgX(r.position_x)
        const y = toSvgY(r.position_y)
        const w = Math.max(toSvgW(r.width_ft), 2)
        const h = Math.max(toSvgH(r.length_ft), 2)
        const { fill, stroke } = roomColor(r.name)
        const label = r.name.replace(/(master |ensuite |common )/i, '').split(' ')[0]

        return (
          <g key={i}>
            <rect
              x={x} y={y} width={w} height={h}
              fill={fill}
              stroke={stroke}
              strokeWidth="1.2"
              rx="1.5"
            />
            {w > 18 && h > 10 && (
              <text
                x={x + w / 2} y={y + h / 2 + 3}
                textAnchor="middle"
                fontSize="5.5"
                fill="#44403c"
                className="select-none"
              >
                {label}
              </text>
            )}
          </g>
        )
      })}
    </svg>
    </div>
  )
}

export default function FloorPlanCard({ alternative, isSelected, onSelect }: FloorPlanCardProps) {
  const variant = alternative.variant
  const borderClass = isSelected
    ? `border-2 ring-4 ${VARIANT_COLORS[variant]}`
    : 'border border-gray-200 dark:border-gray-700'

  return (
    <div
      onClick={onSelect}
      className={`cursor-pointer rounded-xl p-4 bg-white dark:bg-gray-900 shadow-sm hover:shadow-md transition-all ${borderClass}`}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900 dark:text-white capitalize">{variant}</h3>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TEMP_BADGE[variant]}`}>
            t={alternative.temperature_used}
          </span>
          <span
            title={alternative.validation_passed
              ? 'Layout passed all geometric checks'
              : 'Some rooms may extend slightly beyond the buildable zone — still selectable'}
            className={`text-xs px-2 py-0.5 rounded-full font-medium cursor-help ${
              alternative.validation_passed
                ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300'
            }`}>
            {alternative.validation_passed ? 'Passed' : '⚠ Warning'}
          </span>
        </div>
      </div>

      <MiniRoomLayout alternative={alternative} />

      <div className="mt-3 space-y-1.5">
        <ScoreBar label="Space utilisation" value={alternative.scores.space_utilisation} />
        <ScoreBar label="Natural light"     value={alternative.scores.natural_light} />
        <ScoreBar label="Adjacency"         value={alternative.scores.adjacency} />
        <ScoreBar label="Ventilation"       value={alternative.scores.ventilation} />
        <ScoreBar label="Overall"           value={alternative.scores.overall} />
      </div>

      <div className="mt-3 border-t border-gray-100 dark:border-gray-800 pt-3">
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
          {alternative.total_built_area_sqft.toFixed(0)} sqft total · {alternative.rooms.length} rooms
        </p>
        <div className="space-y-2 max-h-40 overflow-y-auto">
          {(() => {
            const floors = [...new Set(alternative.rooms.map((r: Room) => r.floor ?? 1))].sort()
            const multiFloor = floors.length > 1
            return floors.map(floorNum => (
              <div key={floorNum}>
                {multiFloor && (
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-0.5">
                    Floor {floorNum}
                  </p>
                )}
                <ul className="space-y-0.5">
                  {alternative.rooms
                    .filter((r: Room) => (r.floor ?? 1) === floorNum)
                    .map((r: Room, i: number) => (
                      <li key={i} className="text-xs text-gray-600 dark:text-gray-300 flex justify-between">
                        <span>{r.name}</span>
                        <span className="text-gray-400 dark:text-gray-500 tabular-nums">
                          {r.width_ft.toFixed(0)} × {r.length_ft.toFixed(0)} ft
                        </span>
                      </li>
                    ))}
                </ul>
              </div>
            ))
          })()}
        </div>
      </div>
    </div>
  )
}
