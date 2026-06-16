import type { FloorPlanAlternative } from '../types'
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

function MiniRoomLayout({ alternative }: { alternative: FloorPlanAlternative }) {
  const SIZE = 200
  const PAD = 8
  const inner = SIZE - PAD * 2

  const rooms = alternative.rooms
  if (!rooms.length) return null

  const allX = rooms.flatMap(r => [r.position_x, r.position_x + r.width_ft])
  const allY = rooms.flatMap(r => [r.position_y, r.position_y + r.length_ft])
  const minX = Math.min(...allX), maxX = Math.max(...allX)
  const minY = Math.min(...allY), maxY = Math.max(...allY)
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1

  const toSvg = (v: number, range: number, min: number) =>
    PAD + ((v - min) / range) * inner

  return (
    <svg
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="w-full rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
    >
      {rooms.map((r, i) => {
        const x = toSvg(r.position_x, rangeX, minX)
        const y = toSvg(r.position_y, rangeY, minY)
        const w = (r.width_ft / rangeX) * inner
        const h = (r.length_ft / rangeY) * inner
        return (
          <g key={i}>
            <rect
              x={x} y={y} width={Math.max(w, 2)} height={Math.max(h, 2)}
              fill="rgba(249,115,22,0.12)"
              stroke="#f97316"
              strokeWidth="1"
              rx="1"
            />
            {w > 20 && h > 10 && (
              <text
                x={x + w / 2} y={y + h / 2 + 3}
                textAnchor="middle"
                fontSize="6"
                fill="#78716c"
                className="select-none"
              >
                {r.name.split(' ')[0]}
              </text>
            )}
          </g>
        )
      })}
    </svg>
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
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${alternative.validation_passed ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300' : 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'}`}>
            {alternative.validation_passed ? 'Passed' : 'Failed'}
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
          {alternative.total_built_area_sqft.toFixed(0)} sqft total
        </p>
        <ul className="space-y-0.5">
          {alternative.rooms.map((r, i) => (
            <li key={i} className="text-xs text-gray-600 dark:text-gray-300">
              {r.name} — {r.width_ft.toFixed(0)} × {r.length_ft.toFixed(0)} ft
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
