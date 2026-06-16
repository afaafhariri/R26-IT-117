import { useState } from 'react'
import PlotPolygonPreview from '../components/PlotPolygonPreview'
import { triggerFloorPlanGeneration, pollFloorPlanStatus } from '../services/apiService'
import type { BuildableZone, CadastralData, FloorPlanAlternative } from '../types'

interface Props {
  jobId: string
  cadastral: CadastralData
  zone: BuildableZone
  onSuccess: (alternatives: FloorPlanAlternative[]) => void
}

const ROAD_BADGE: Record<string, string> = {
  'main road':    'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  'lane':         'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  'private road': 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">
      <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-900 dark:text-white text-right max-w-[60%]">{value}</span>
    </div>
  )
}

export default function LandDataReviewView({ jobId, cadastral, zone, onSuccess }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollMsg, setPollMsg] = useState('')

  const gps = cadastral.gps_coordinates[0]

  const generate = async () => {
    setLoading(true)
    setError(null)
    try {
      await triggerFloorPlanGeneration(jobId)
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
    <div className="max-w-5xl mx-auto px-4 py-10">
      <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Land Data Review</h2>

      <div className="grid md:grid-cols-2 gap-6 mb-6">
        {/* Extracted data */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Extracted Land Data</h3>
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
        </div>

        {/* Plot preview */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm flex flex-col items-center">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3 self-start">Plot Visualisation</h3>
          <PlotPolygonPreview
            plotPolygon={cadastral.plot_boundary_polygon}
            buildablePolygon={zone.buildable_polygon}
            size={260}
          />
        </div>
      </div>

      {/* Regulatory summary */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 shadow-sm mb-6">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Regulatory Summary (NBC Sri Lanka)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 text-gray-500 dark:text-gray-400 w-48">Buildable Area</td>
                <td className="py-2 font-medium text-gray-900 dark:text-white">{zone.buildable_area_sqft.toFixed(0)} sqft</td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 text-gray-500 dark:text-gray-400">Coverage Ratio (BCR)</td>
                <td className="py-2 font-medium text-gray-900 dark:text-white">{(zone.bcr_value * 100).toFixed(0)}%</td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 text-gray-500 dark:text-gray-400">Front Setback</td>
                <td className="py-2 font-medium text-gray-900 dark:text-white">{zone.front_setback_ft.toFixed(1)} ft</td>
              </tr>
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 text-gray-500 dark:text-gray-400">Rear Setback</td>
                <td className="py-2 font-medium text-gray-900 dark:text-white">{zone.rear_setback_ft.toFixed(1)} ft</td>
              </tr>
              <tr>
                <td className="py-2 text-gray-500 dark:text-gray-400">Side Setbacks</td>
                <td className="py-2 font-medium text-gray-900 dark:text-white">
                  {zone.side_setbacks_ft.map(v => `${v.toFixed(1)} ft`).join(', ')}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">{zone.constraints_summary}</p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-xl text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}
      {loading && pollMsg && (
        <p className="mb-4 text-sm text-orange-600 dark:text-orange-400 text-center">{pollMsg}</p>
      )}

      <button
        onClick={generate}
        disabled={loading}
        className="w-full py-3 px-6 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Generating Floor Plans…
          </>
        ) : 'Generate Floor Plan Options'}
      </button>
    </div>
  )
}
