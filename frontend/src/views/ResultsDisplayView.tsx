import { useEffect, useRef, useState } from 'react'
import JsonViewer from '../components/JsonViewer'
import PdfViewer from '../components/PdfViewer'
import ProductCard from '../components/ProductCard'
import SvgViewer from '../components/SvgViewer'
import { getDownloadUrl } from '../services/apiService'
import type { FullDesignPackage } from '../types'

interface Props {
  pkg: FullDesignPackage
  onReset: () => void
}

const NAV_ITEMS = [
  { id: 'floor-plan',    label: 'Floor Plan Drawing' },
  { id: 'renders',       label: 'Photorealistic Renders' },
  { id: 'video',         label: '3D Video Tour' },
  { id: 'walkthrough',   label: 'Voice Walkthrough' },
  { id: 'blueprint',     label: '2D Blueprint' },
  { id: 'floorplan3d',   label: '3D Floor Plan' },
  { id: 'shopping',      label: 'Shopping List' },
  { id: 'pdf',           label: 'PDF Report' },
  { id: 'schema',        label: 'Building Schema' },
]

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mb-16 scroll-mt-20">
      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 pb-2 border-b border-gray-200 dark:border-gray-800">
        {title}
      </h3>
      {children}
    </section>
  )
}

function WalkthroughPlayer({ script }: { script: string }) {
  const [playing, setPlaying] = useState(false)
  const [highlighted, setHighlighted] = useState(-1)
  const sentences = script.match(/[^.!?]+[.!?]+/g) ?? [script]
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null)

  const play = () => {
    const utter = new SpeechSynthesisUtterance(script)
    utter.lang = 'en-US'
    let idx = 0
    utter.onboundary = (e) => {
      const pos = e.charIndex
      let count = 0
      for (let i = 0; i < sentences.length; i++) {
        count += sentences[i].length
        if (pos < count) { setHighlighted(i); break }
      }
    }
    utter.onend = () => { setPlaying(false); setHighlighted(-1) }
    utterRef.current = utter
    window.speechSynthesis.speak(utter)
    setPlaying(true)
    idx
  }

  const stop = () => {
    window.speechSynthesis.cancel()
    setPlaying(false)
    setHighlighted(-1)
  }

  useEffect(() => () => window.speechSynthesis.cancel(), [])

  return (
    <div>
      <button
        onClick={playing ? stop : play}
        className="mb-4 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
      >
        {playing ? (
          <><svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><rect x="5" y="4" width="3" height="12" rx="1" /><rect x="12" y="4" width="3" height="12" rx="1" /></svg> Stop</>
        ) : (
          <><svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" /></svg> Play Walkthrough</>
        )}
      </button>
      <div className="bg-gray-50 dark:bg-gray-900 rounded-xl p-5 text-sm leading-relaxed text-gray-700 dark:text-gray-300 space-y-1">
        {sentences.map((s, i) => (
          <span
            key={i}
            className={`transition-colors ${i === highlighted ? 'bg-orange-100 dark:bg-orange-900/40 rounded px-0.5' : ''}`}
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function ResultsDisplayView({ pkg, onReset }: Props) {
  const viz = pkg.visualization_assets
  const [lightbox, setLightbox] = useState<string | null>(null)

  const imgSrc = (b64: string) => `data:image/png;base64,${b64}`

  return (
    <div className="flex">
      {/* Sidebar */}
      <nav className="hidden lg:block w-56 shrink-0 sticky top-16 self-start h-[calc(100vh-4rem)] overflow-y-auto border-r border-gray-200 dark:border-gray-800 py-6 px-4">
        <p className="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider mb-3">Sections</p>
        <ul className="space-y-1">
          {NAV_ITEMS.map(item => (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className="block text-sm text-gray-600 dark:text-gray-400 hover:text-orange-500 dark:hover:text-orange-400 py-1 px-2 rounded-lg hover:bg-orange-50 dark:hover:bg-orange-950/20 transition-colors"
              >
                {item.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {/* Main content */}
      <main className="flex-1 min-w-0 px-4 lg:px-8 py-8 max-w-4xl">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Your Design Package</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {pkg.selected_plan.variant} plan — {pkg.selected_plan.total_built_area_sqft.toFixed(0)} sqft
            </p>
          </div>
          <button onClick={onReset} className="text-sm text-orange-500 hover:text-orange-600 font-medium">
            Start New Design
          </button>
        </div>

        <Section id="floor-plan" title="Floor Plan Drawing">
          <SvgViewer jobId={pkg.job_id} />
          <a
            href={getDownloadUrl('svg', pkg.job_id)}
            download
            className="mt-3 inline-block text-sm text-orange-500 hover:text-orange-600 font-medium"
          >
            Download SVG
          </a>
        </Section>

        <Section id="renders" title="Photorealistic Renders">
          <div className="grid md:grid-cols-2 gap-4">
            {[
              { src: viz.exterior_image_base64, label: 'Exterior' },
              { src: viz.interior_image_base64, label: 'Interior' },
            ].map(({ src, label }) => (
              <div key={label} className="relative group cursor-zoom-in" onClick={() => setLightbox(imgSrc(src))}>
                <img
                  src={imgSrc(src)}
                  alt={label}
                  className="w-full rounded-xl border border-gray-200 dark:border-gray-700 object-cover"
                />
                <div className="absolute bottom-2 left-2 bg-black/50 text-white text-xs px-2 py-0.5 rounded">{label}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section id="video" title="3D Video Tour">
          {viz.video_url ? (
            <video src={viz.video_url} controls loop muted className="w-full rounded-xl border border-gray-200 dark:border-gray-700" />
          ) : (
            <div className="bg-gray-100 dark:bg-gray-800 rounded-xl p-8 flex flex-col items-center gap-2 text-center">
              <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              <p className="text-sm text-gray-500 dark:text-gray-400">{viz.video_skipped_reason}</p>
            </div>
          )}
        </Section>

        <Section id="walkthrough" title="Voice Walkthrough">
          <WalkthroughPlayer script={viz.walkthrough_script} />
        </Section>

        <Section id="blueprint" title="2D Blueprint">
          <img src={imgSrc(viz.blueprint_2d_image_base64)} alt="2D Blueprint" className="w-full rounded-xl border border-gray-200 dark:border-gray-700" />
          <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">{viz.blueprint_2d_description}</p>
        </Section>

        <Section id="floorplan3d" title="3D Floor Plan">
          <img src={imgSrc(viz.floorplan_3d_image_base64)} alt="3D Floor Plan" className="w-full rounded-xl border border-gray-200 dark:border-gray-700" />
          <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">{viz.floorplan_3d_description}</p>
        </Section>

        <Section id="shopping" title="Shopping List">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {viz.shopping_list.map((item, i) => <ProductCard key={i} item={item} />)}
          </div>
        </Section>

        <Section id="pdf" title="PDF Report">
          <PdfViewer url={getDownloadUrl('pdf', pkg.job_id)} />
          <a
            href={getDownloadUrl('pdf', pkg.job_id)}
            download
            className="mt-3 inline-block text-sm text-orange-500 hover:text-orange-600 font-medium"
          >
            Download PDF
          </a>
        </Section>

        <Section id="schema" title="Building Schema">
          <JsonViewer data={pkg.building_schema_json} />
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            This schema has been sent to Component 02 for cost estimation.
          </p>
        </Section>

        <button onClick={onReset} className="w-full py-3 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-xl transition-colors">
          Start a New Design
        </button>
      </main>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 cursor-zoom-out"
          onClick={() => setLightbox(null)}
        >
          <img src={lightbox} alt="Full screen" className="max-w-full max-h-full rounded-xl object-contain" />
        </div>
      )}
    </div>
  )
}
