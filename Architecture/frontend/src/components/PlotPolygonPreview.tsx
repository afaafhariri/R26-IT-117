interface PlotPolygonPreviewProps {
  plotPolygon: [number, number][]
  buildablePolygon: [number, number][]
  size?: number
}

function makeBounds(points: [number, number][]) {
  const xs = points.map(p => p[0])
  const ys = points.map(p => p[1])
  return {
    minX: Math.min(...xs), maxX: Math.max(...xs),
    minY: Math.min(...ys), maxY: Math.max(...ys),
  }
}

function toSvgPoints(
  points: [number, number][],
  bounds: ReturnType<typeof makeBounds>,
  size: number,
  pad: number,
): string {
  if (!points.length) return ''
  const { minX, maxX, minY, maxY } = bounds
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1
  const inner = size - pad * 2
  return points
    .map(([x, y]) => [
      pad + ((x - minX) / rangeX) * inner,
      pad + ((y - minY) / rangeY) * inner,
    ])
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ')
}

export default function PlotPolygonPreview({
  plotPolygon,
  buildablePolygon,
  size = 300,
}: PlotPolygonPreviewProps) {
  const pad = size * 0.08
  // Use the plot polygon's bounds for BOTH polygons so buildable zone
  // appears correctly inset inside the full plot shape.
  const bounds = plotPolygon.length ? makeBounds(plotPolygon) : makeBounds(buildablePolygon)

  return (
    <div className="flex flex-col items-center gap-2">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
      >
        {plotPolygon.length > 0 && (
          <polygon
            points={toSvgPoints(plotPolygon, bounds, size, pad)}
            fill="rgba(156,163,175,0.3)"
            stroke="#6b7280"
            strokeWidth="2"
          />
        )}
        {buildablePolygon.length > 0 && (
          <polygon
            points={toSvgPoints(buildablePolygon, bounds, size, pad)}
            fill="rgba(34,197,94,0.35)"
            stroke="#22c55e"
            strokeWidth="2"
            strokeDasharray="6 3"
          />
        )}
      </svg>
      <div className="flex gap-4 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 bg-gray-400 opacity-50 rounded-sm" /> Full plot
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 bg-green-400 opacity-60 rounded-sm" /> Buildable zone
        </span>
      </div>
    </div>
  )
}
