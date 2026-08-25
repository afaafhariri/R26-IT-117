import { useEffect, useState } from 'react'
import JsonViewer from '../components/JsonViewer'
import ProductCard from '../components/ProductCard'
import { generateVideo } from '../services/apiService'
import type { FullDesignPackage, VideoAsset } from '../types'

interface Props {
  pkg: FullDesignPackage
  onReset: () => void
}

const NAV_SECTIONS = [
  { id: 'renders',   label: 'Photorealistic Renders' },
  { id: 'blueprint', label: '2D Blueprint' },
  { id: 'floorplan', label: '3D Floor Plan' },
  { id: 'walkthrough', label: 'Voice Walkthrough' },
  { id: 'shopping',  label: 'Shopping List' },
  { id: 'schema',    label: 'Building Schema' },
  { id: 'video',     label: 'Video Tour' },
]

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mb-16 scroll-mt-24">
      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-5 pb-2 border-b border-gray-200 dark:border-gray-800">
        {title}
      </h3>
      {children}
    </section>
  )
}

function B64Image({ b64, alt, className }: { b64: string; alt: string; className?: string }) {
  const [lightbox, setLightbox] = useState(false)
  return (
    <>
      <img
        src={`data:image/png;base64,${b64}`}
        alt={alt}
        className={`cursor-zoom-in rounded-xl object-cover ${className ?? ''}`}
        onClick={() => setLightbox(true)}
      />
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setLightbox(false)}
        >
          <img
            src={`data:image/png;base64,${b64}`}
            alt={alt}
            className="max-w-full max-h-full rounded-xl object-contain"
          />
          <button
            className="absolute top-4 right-4 text-white/70 hover:text-white text-3xl leading-none"
            onClick={() => setLightbox(false)}
          >
            ✕
          </button>
        </div>
      )}
    </>
  )
}

function B64DownloadButton({ b64, filename, label }: { b64: string; filename: string; label: string }) {
  const download = () => {
    const link = document.createElement('a')
    link.href = `data:image/png;base64,${b64}`
    link.download = filename
    link.click()
  }
  return (
    <button
      onClick={download}
      className="mt-3 inline-flex items-center gap-1.5 text-sm text-orange-500 hover:text-orange-600 font-medium"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
      {label}
    </button>
  )
}

export default function ResultsDisplayView({ pkg, onReset }: Props) {
  const viz = pkg.visualization_assets
  const plan = pkg.selected_plan

  // Active nav section tracking
  const [activeSection, setActiveSection] = useState('renders')
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActiveSection(entry.target.id)
        }
      },
      { rootMargin: '-30% 0px -60% 0px' },
    )
    NAV_SECTIONS.forEach(s => {
      const el = document.getElementById(s.id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [])

  // Voice walkthrough
  const [speaking, setSpeaking] = useState(false)
  const [highlightedSentence, setHighlightedSentence] = useState<number | null>(null)
  const sentences = viz.walkthrough_script
    .split(/(?<=[.!?])\s+/)
    .filter(s => s.trim().length > 0)

  const playWalkthrough = () => {
    if (speaking) {
      window.speechSynthesis.cancel()
      setSpeaking(false)
      setHighlightedSentence(null)
      return
    }
    setSpeaking(true)
    setHighlightedSentence(0)
    const utt = new SpeechSynthesisUtterance(viz.walkthrough_script)
    utt.lang = 'en-US'
    utt.rate = 0.9
    utt.onboundary = (e) => {
      const charIdx = e.charIndex
      let count = 0
      for (let i = 0; i < sentences.length; i++) {
        count += sentences[i].length + 1
        if (charIdx < count) {
          setHighlightedSentence(i)
          break
        }
      }
    }
    utt.onend = () => {
      setSpeaking(false)
      setHighlightedSentence(null)
    }
    window.speechSynthesis.speak(utt)
  }

  // Schema copy
  const [copied, setCopied] = useState(false)
  const copySchema = () => {
    navigator.clipboard.writeText(JSON.stringify(pkg.building_schema_json, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Video generation
  const [videoState, setVideoState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [videoAsset, setVideoAsset] = useState<VideoAsset | null>(pkg.video ?? null)

  const handleGenerateVideo = async () => {
    setVideoState('loading')
    try {
      const asset = await generateVideo(pkg.job_id)
      setVideoAsset(asset)
      setVideoState('done')
    } catch (err) {
      setVideoState('error')
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Sticky sidebar */}
      <aside className="hidden lg:block w-52 shrink-0">
        <div className="sticky top-20 pt-10 pl-4">
          <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-3">
            Contents
          </p>
          <nav className="space-y-1">
            {NAV_SECTIONS.map(s => (
              <a
                key={s.id}
                href={`#${s.id}`}
                className={`block text-sm px-3 py-1.5 rounded-lg transition-colors
                  ${activeSection === s.id
                    ? 'bg-orange-50 dark:bg-orange-950/30 text-orange-600 dark:text-orange-400 font-medium'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                  }`}
              >
                {s.label}
              </a>
            ))}
          </nav>

          <button
            onClick={onReset}
            className="mt-8 text-sm text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          >
            ← New Design
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 max-w-4xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="flex items-start justify-between mb-10">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Your Full Design Package</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {plan.variant} plan · {plan.total_built_area_sqft.toFixed(0)} sqft built
            </p>
          </div>
          <button
            onClick={onReset}
            className="text-sm text-orange-500 hover:text-orange-600 font-medium lg:hidden"
          >
            New Design
          </button>
        </div>

        {/* Score chips */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-12">
          {[
            { label: 'Space Use',      value: plan.scores.space_utilisation },
            { label: 'Natural Light',  value: plan.scores.natural_light },
            { label: 'Adjacency',      value: plan.scores.adjacency },
            { label: 'Ventilation',    value: plan.scores.ventilation },
          ].map(({ label, value }) => (
            <div key={label} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-orange-500">{value.toFixed(1)}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{label}</div>
            </div>
          ))}
        </div>

        {/* 1. Photorealistic Renders */}
        <Section id="renders" title="Photorealistic Renders">
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-2 font-medium uppercase tracking-wide">Exterior</p>
              <B64Image b64={viz.exterior_image_base64} alt="Exterior render" className="w-full aspect-video" />
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-2 font-medium uppercase tracking-wide">Interior</p>
              <B64Image b64={viz.interior_image_base64} alt="Interior render" className="w-full aspect-video" />
            </div>
          </div>
          <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">Click any image to enlarge.</p>
        </Section>

        {/* 2. 2D Blueprint */}
        <Section id="blueprint" title="2D Blueprint">
          <B64Image b64={viz.blueprint_2d_image_base64} alt="2D blueprint" className="w-full" />
          <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">{viz.blueprint_2d_description}</p>
          <B64DownloadButton b64={viz.blueprint_2d_image_base64} filename={`blueprint_${pkg.job_id}.png`} label="Download Blueprint" />
        </Section>

        {/* 3. 3D Floor Plan */}
        <Section id="floorplan" title="3D Floor Plan">
          <B64Image b64={viz.floorplan_3d_image_base64} alt="3D floor plan" className="w-full" />
          <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">{viz.floorplan_3d_description}</p>
          <B64DownloadButton b64={viz.floorplan_3d_image_base64} filename={`floorplan3d_${pkg.job_id}.png`} label="Download 3D Floor Plan" />
        </Section>

        {/* 4. Voice Walkthrough */}
        <Section id="walkthrough" title="Voice Walkthrough">
          <div className="flex items-center gap-3 mb-5">
            <button
              onClick={playWalkthrough}
              className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium text-sm transition-colors
                ${speaking
                  ? 'bg-red-100 dark:bg-red-950/40 text-red-600 dark:text-red-400 hover:bg-red-200'
                  : 'bg-orange-500 hover:bg-orange-600 text-white'
                }`}
            >
              {speaking ? (
                <>
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="4" width="4" height="16" rx="1" />
                    <rect x="14" y="4" width="4" height="16" rx="1" />
                  </svg>
                  Stop
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                  Play Walkthrough
                </>
              )}
            </button>
            {speaking && (
              <span className="text-xs text-orange-500 animate-pulse">Speaking…</span>
            )}
          </div>
          <div className="bg-gray-50 dark:bg-gray-900/60 rounded-xl p-5 text-sm leading-relaxed text-gray-700 dark:text-gray-300 space-y-1">
            {sentences.map((sentence, i) => (
              <span
                key={i}
                className={`transition-colors ${
                  highlightedSentence === i
                    ? 'bg-orange-100 dark:bg-orange-950/50 text-orange-900 dark:text-orange-200 rounded px-0.5'
                    : ''
                }`}
              >
                {sentence}{' '}
              </span>
            ))}
          </div>
        </Section>

        {/* 5. Shopping List */}
        <Section id="shopping" title="Shopping List">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {viz.shopping_list.map((item, i) => (
              <ProductCard key={i} item={item} />
            ))}
          </div>
        </Section>

        {/* 6. Building Schema */}
        <Section id="schema" title="Building Schema">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Sent to Component 02 for cost estimation.
            </p>
            <button
              onClick={copySchema}
              className="text-sm text-orange-500 hover:text-orange-600 font-medium inline-flex items-center gap-1.5"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              {copied ? 'Copied!' : 'Copy JSON'}
            </button>
          </div>
          <JsonViewer data={pkg.building_schema_json} />
        </Section>

        {/* 7. Video Tour */}
        <Section id="video" title="Video Tour">
          {videoState === 'idle' && !videoAsset && (
            <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl p-8 text-center">
              <div className="text-5xl mb-4">🎬</div>
              <h4 className="font-semibold text-gray-900 dark:text-white mb-2">
                Generate a Video Walkthrough
              </h4>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                AI-generated cinematic walkthrough of your home design using Google Veo 2.0.
                Limited to 1 video per hour.
              </p>
              <button
                onClick={handleGenerateVideo}
                className="px-6 py-3 bg-orange-500 hover:bg-orange-600 text-white font-semibold rounded-xl transition-colors"
              >
                Generate Video Tour
              </button>
            </div>
          )}

          {videoState === 'loading' && (
            <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl p-8 text-center">
              <div className="flex items-center justify-center mb-4">
                <div className="relative w-12 h-12">
                  <div className="absolute inset-0 rounded-full border-4 border-orange-100 dark:border-orange-900" />
                  <div className="absolute inset-0 rounded-full border-4 border-orange-500 border-t-transparent animate-spin" />
                </div>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Generating video walkthrough… this may take 1–3 minutes.
              </p>
            </div>
          )}

          {videoState === 'done' && videoAsset && !videoAsset.skipped && videoAsset.video_base64 && (
            <div>
              <video
                src={videoAsset.video_base64.startsWith('data:')
                  ? videoAsset.video_base64
                  : videoAsset.video_base64}
                controls
                className="w-full rounded-xl"
              />
            </div>
          )}

          {videoState === 'done' && videoAsset?.skipped && (
            <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-5">
              <p className="text-sm text-amber-800 dark:text-amber-300 font-medium">
                Video generation rate limited
              </p>
              <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
                {videoAsset.skip_reason}
              </p>
              {videoAsset.minutes_until_available && (
                <p className="text-xs text-amber-600 dark:text-amber-500 mt-2">
                  Available again in approximately {videoAsset.minutes_until_available} minute(s).
                </p>
              )}
            </div>
          )}

          {videoState === 'error' && (
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-xl p-5">
              <p className="text-sm text-red-700 dark:text-red-400">
                Video generation failed. Please try again later.
              </p>
            </div>
          )}
        </Section>

        <button
          onClick={onReset}
          className="w-full py-3 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-xl transition-colors"
        >
          Start a New Design
        </button>
      </main>
    </div>
  )
}
