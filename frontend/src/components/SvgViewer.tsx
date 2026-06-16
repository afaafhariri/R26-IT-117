import { useEffect, useState } from 'react'
import { getDownloadUrl } from '../services/apiService'

export default function SvgViewer({ jobId }: { jobId: string }) {
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(getDownloadUrl('svg', jobId))
      .then(r => r.text())
      .then(setSvg)
      .catch(() => setError(true))
  }, [jobId])

  if (error) return <p className="text-sm text-red-500">Could not load SVG.</p>
  if (!svg) return (
    <div className="h-48 bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse flex items-center justify-center text-gray-400 text-sm">
      Loading floor plan…
    </div>
  )

  return (
    <div
      className="w-full overflow-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-2"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
