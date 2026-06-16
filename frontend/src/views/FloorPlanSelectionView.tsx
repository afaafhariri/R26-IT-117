import { useState } from 'react'
import FloorPlanCard from '../components/FloorPlanCard'
import { selectPlan } from '../services/apiService'
import type { FloorPlanAlternative, FullDesignPackage } from '../types'

interface Props {
  jobId: string
  alternatives: FloorPlanAlternative[]
  onSuccess: (pkg: FullDesignPackage) => void
  onGenerating: () => void
}

export default function FloorPlanSelectionView({ jobId, alternatives, onSuccess, onGenerating }: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const generate = async () => {
    if (!selected) return
    setLoading(true)
    setError(null)
    onGenerating()
    try {
      const pkg = await selectPlan(jobId, selected)
      onSuccess(pkg)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed.')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-10">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Choose a Floor Plan</h2>
      <p className="text-gray-500 dark:text-gray-400 mb-6">
        Select one of the three AI-generated alternatives to build your full design package.
      </p>

      <div className="grid md:grid-cols-3 gap-5 mb-8">
        {alternatives.map(alt => (
          <FloorPlanCard
            key={alt.variant}
            alternative={alt}
            isSelected={selected === alt.variant}
            onSelect={() => setSelected(alt.variant)}
          />
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      <button
        onClick={generate}
        disabled={!selected || loading}
        className="w-full py-3 px-6 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Generating Full Design Package…
          </>
        ) : selected ? `Generate Full Design Package — ${selected}` : 'Select a plan above'}
      </button>
    </div>
  )
}
