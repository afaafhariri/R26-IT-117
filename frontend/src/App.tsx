import { useEffect, useState } from 'react'
import Header from './components/Header'
import type { AppState, BuildableZone, CadastralData, FloorPlanAlternative, FullDesignPackage } from './types'
import FloorPlanSelectionView from './views/FloorPlanSelectionView'
import GenerationProgressView from './views/GenerationProgressView'
import LandDataReviewView from './views/LandDataReviewView'
import ResultsDisplayView from './views/ResultsDisplayView'
import UploadView from './views/UploadView'

const INITIAL_STATE: AppState = {
  currentView: 'upload',
  jobId: null,
  cadastralData: null,
  buildableZone: null,
  floorPlanAlternatives: [],
  selectedVariant: null,
  generationLog: [],
  fullDesignPackage: null,
  error: null,
  theme: 'light',
}

export default function App() {
  const [state, setState] = useState<AppState>(INITIAL_STATE)

  // Sync dark class with theme
  useEffect(() => {
    document.documentElement.classList.toggle('dark', state.theme === 'dark')
  }, [state.theme])

  const set = (patch: Partial<AppState>) => setState(prev => ({ ...prev, ...patch }))

  const toggleTheme = () =>
    set({ theme: state.theme === 'light' ? 'dark' : 'light' })

  const onUploadSuccess = (jobId: string, cadastralData: CadastralData, buildableZone: BuildableZone) =>
    set({ jobId, cadastralData, buildableZone, currentView: 'land-review' })

  const onAlternativesReady = (alternatives: FloorPlanAlternative[]) =>
    set({ floorPlanAlternatives: alternatives, currentView: 'plan-selection' })

  const onGenerating = () => set({ currentView: 'generating' })

  const onPackageReady = (pkg: FullDesignPackage) =>
    set({ fullDesignPackage: pkg, currentView: 'results' })

  const onReset = () => setState(INITIAL_STATE)

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 transition-colors">
      <Header theme={state.theme} onToggleTheme={toggleTheme} />

      {state.currentView === 'upload' && (
        <UploadView onSuccess={onUploadSuccess} />
      )}

      {state.currentView === 'land-review' && state.cadastralData && state.buildableZone && (
        <LandDataReviewView
          jobId={state.jobId!}
          cadastral={state.cadastralData}
          zone={state.buildableZone}
          onSuccess={onAlternativesReady}
        />
      )}

      {state.currentView === 'plan-selection' && (
        <FloorPlanSelectionView
          jobId={state.jobId!}
          alternatives={state.floorPlanAlternatives}
          onSuccess={onPackageReady}
          onGenerating={onGenerating}
        />
      )}

      {state.currentView === 'generating' && (
        <GenerationProgressView />
      )}

      {state.currentView === 'results' && state.fullDesignPackage && (
        <ResultsDisplayView pkg={state.fullDesignPackage} onReset={onReset} />
      )}
    </div>
  )
}
