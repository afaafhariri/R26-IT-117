import { useEffect, useState } from 'react'

const STAGES = [
  { label: 'Preparing your design data',      icon: '📋', duration: 3 },
  { label: 'Sending to cost estimation',       icon: '💰', duration: 2 },
  { label: 'Rendering exterior view',          icon: '🏠', duration: 9 },
  { label: 'Rendering interior view',          icon: '🛋️',  duration: 9 },
  { label: 'Drawing 2D blueprint',             icon: '📐', duration: 9 },
  { label: 'Creating 3D floor plan',           icon: '🏗️',  duration: 9 },
  { label: 'Writing walkthrough script',       icon: '📝', duration: 5 },
  { label: 'Curating shopping list',           icon: '🛍️',  duration: 5 },
]

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
      }, STAGES[idx].duration * 1000)
    }

    advance()
    return () => clearTimeout(timer)
  }, [])

  const totalDone = done.filter(Boolean).length
  const progress = Math.round((totalDone / STAGES.length) * 100)

  return (
    <div className="min-h-[80vh] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Spinner */}
        <div className="flex items-center justify-center mb-6">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 rounded-full border-4 border-orange-100 dark:border-orange-900" />
            <div className="absolute inset-0 rounded-full border-4 border-orange-500 border-t-transparent animate-spin" />
          </div>
        </div>

        <h2 className="text-xl font-bold text-gray-900 dark:text-white text-center mb-1">
          Building Your Full Design Package
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center mb-4">
          {currentStage < STAGES.length ? STAGES[currentStage].label : 'Finalising…'}
        </p>

        {/* Progress bar */}
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mb-6">
          <div
            className="bg-orange-500 h-1.5 rounded-full transition-all duration-700"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Steps list */}
        <div className="space-y-3">
          {STAGES.map((stage, i) => {
            const isDone = done[i]
            const isCurrent = i === currentStage && !isDone
            const isPending = i > currentStage

            return (
              <div key={i} className="flex items-center gap-3">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-sm transition-colors
                  ${isDone ? 'bg-green-500' : isCurrent ? 'bg-orange-500' : 'bg-gray-200 dark:bg-gray-700'}`}
                >
                  {isDone ? (
                    <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isCurrent ? (
                    <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                  ) : (
                    <span className="text-xs text-gray-400">{i + 1}</span>
                  )}
                </div>
                <span className={`text-sm transition-colors flex-1
                  ${isDone ? 'text-gray-400 dark:text-gray-500 line-through' :
                    isCurrent ? 'text-gray-900 dark:text-white font-medium' :
                    isPending ? 'text-gray-400 dark:text-gray-600' : ''}`}
                >
                  {stage.label}
                </span>
                {isDone && (
                  <span className="text-xs text-green-500">Done</span>
                )}
                {isCurrent && (
                  <span className="text-xs text-orange-500 animate-pulse">Running…</span>
                )}
              </div>
            )
          })}
        </div>

        <p className="mt-8 text-xs text-gray-400 dark:text-gray-600 text-center">
          AI image generation takes ~30–60 seconds. Please wait.
        </p>
      </div>
    </div>
  )
}
