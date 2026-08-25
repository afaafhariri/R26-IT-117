import { useCallback, useRef, useState } from 'react'
import { uploadCadastral } from '../services/apiService'
import type { BuildableZone, CadastralData } from '../types'

interface Props {
  onSuccess: (jobId: string, cadastral: CadastralData, zone: BuildableZone) => void
}

const ACCEPTED = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff']
const MAX_MB = 20

export default function UploadView({ onSuccess }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    setError(null)
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`File exceeds ${MAX_MB}MB limit.`)
      return
    }
    setFile(f)
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }, [])

  const onSubmit = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const res = await uploadCadastral(file)
      onSuccess(res.job_id, res.cadastral_data, res.buildable_zone)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-xl">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white text-center mb-2">
          AI Construction Planner
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-center mb-8">
          Upload your Sri Lankan cadastral plan and get AI-generated floor plans in minutes.
        </p>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`cursor-pointer border-2 border-dashed rounded-2xl p-10 flex flex-col items-center gap-3 transition-colors
            ${dragging
              ? 'border-orange-400 bg-orange-50 dark:bg-orange-950/20'
              : 'border-gray-300 dark:border-gray-700 hover:border-orange-400 hover:bg-orange-50 dark:hover:bg-orange-950/10'
            }`}
        >
          <svg className="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          {file ? (
            <div className="text-center">
              <p className="font-medium text-gray-900 dark:text-white">{file.name}</p>
              <p className="text-sm text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
          ) : (
            <div className="text-center">
              <p className="font-medium text-gray-700 dark:text-gray-300">Drop your cadastral plan here</p>
              <p className="text-sm text-gray-500">or click to browse</p>
              <p className="text-xs text-gray-400 mt-1">PDF, PNG, JPG, TIFF — max {MAX_MB}MB</p>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED.join(',')}
            className="hidden"
            onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
        </div>

        {/* What it does */}
        <ul className="mt-6 space-y-2 text-sm text-gray-600 dark:text-gray-400">
          {[
            'Reads your land details automatically using AI OCR and NER',
            'Applies NBC Sri Lanka building regulations to find your legal buildable zone',
            'Generates 3 floor plan alternatives with AI and produces a full design package',
          ].map((text, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-0.5 w-5 h-5 rounded-full bg-orange-100 dark:bg-orange-900 text-orange-600 dark:text-orange-400 flex items-center justify-center text-xs font-bold shrink-0">
                {i + 1}
              </span>
              {text}
            </li>
          ))}
        </ul>

        {error && (
          <div className="mt-4 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-400 text-sm">
            {error}
          </div>
        )}

        <button
          onClick={onSubmit}
          disabled={!file || loading}
          className="mt-6 w-full py-3 px-6 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Analysing your cadastral plan…
            </>
          ) : 'Process My Land Plan'}
        </button>
      </div>
    </div>
  )
}
