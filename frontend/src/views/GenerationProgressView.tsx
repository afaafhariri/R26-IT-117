import { useEffect, useState } from 'react'

const STAGES = [
  'Drawing SVG floor plan',
  'Generating PDF report',
  'Sending to cost estimation',
  'Rendering exterior view',
  'Rendering interior view',
  'Drawing 2D blueprint',
  'Creating 3D floor plan',
  'Writing walkthrough script',
  'Curating shopping list',
  'Generating video tour',
]

const STAGE_DURATIONS = [4, 5, 3, 12, 12, 12, 12, 8, 8, 20]

export default function GenerationProgressView() {
  const [currentStage, setCurrentStage] = useState(0)
  const [done, setDone] = useState<boolean[]>(new Array(STAGES.length).fill(false))

  useEffect(() => {
    let idx = 0
    let timer: ReturnType<typeof setTimeout>

    const advance = () => {
      if (idx >= STAGES.length) return
      setCurrentStage(idx)
      timer = setTimeout(() => {
        setDone(prev => {
          const next = [...prev]
          next[idx] = true
          return next
        })
        idx++
        advance()
      }, STAGE_DURATIONS[idx] * 1000)
    }

    advance()
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="min-h-[80vh] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-center mb-6">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 rounded-full border-4 border-orange-100 dark:border-orange-900" />
            <div className="absolute inset-0 rounded-full border-4 border-orange-500 border-t-transparent animate-spin" />
          </div>
        </div>

        <h2 className="text-xl font-bold text-gray-900 dark:text-white text-center mb-1">
          Building Your Design Package
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center mb-8">
          {currentStage < STAGES.length ? STAGES[currentStage] : 'Finalising…'}
        </p>

        <div className="space-y-3">
          {STAGES.map((stage, i) => {
            const isDone = done[i]
            const isCurrent = i === currentStage && !isDone
            const isPending = i > currentStage

            return (
              <div key={i} className="flex items-center gap-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 transition-colors
                  ${isDone ? 'bg-green-500' : isCurrent ? 'bg-orange-500' : 'bg-gray-200 dark:bg-gray-700'}`}
                >
                  {isDone ? (
                    <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isCurrent ? (
                    <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                  ) : (
                    <div className="w-2 h-2 bg-gray-400 rounded-full" />
                  )}
                </div>
                <span className={`text-sm transition-colors
                  ${isDone ? 'text-gray-400 dark:text-gray-500 line-through' :
                    isCurrent ? 'text-gray-900 dark:text-white font-medium' :
                    isPending ? 'text-gray-400 dark:text-gray-600' : ''}`}
                >
                  {stage}
                </span>
              </div>
            )
          })}
        </div>

        <p className="mt-8 text-xs text-gray-400 dark:text-gray-600 text-center">
          This typically takes 2–4 minutes. Please do not close this page.
        </p>
      </div>
    </div>
  )
}
