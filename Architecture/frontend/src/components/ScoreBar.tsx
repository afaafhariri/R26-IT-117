interface ScoreBarProps {
  label: string
  value: number  // 0–10
}

export default function ScoreBar({ label, value }: ScoreBarProps) {
  const pct = Math.min(100, (value / 10) * 100)
  const color = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-red-400'

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-500 dark:text-gray-400 w-28 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium w-6 text-right text-gray-700 dark:text-gray-300">
        {value.toFixed(1)}
      </span>
    </div>
  )
}
