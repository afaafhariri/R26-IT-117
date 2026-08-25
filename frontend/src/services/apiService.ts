import type {
  BuildableZone,
  CadastralData,
  FloorPlanAlternative,
  FullDesignPackage,
  VideoAsset,
} from '../types'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function uploadCadastral(
  file: File,
): Promise<{ job_id: string; cadastral_data: CadastralData; buildable_zone: BuildableZone }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/process-cadastral`, { method: 'POST', body: form })
  return handleResponse(res)
}

export interface UserRequirements {
  bedrooms: number
  bathrooms: number
  living_room: boolean
  kitchen: boolean
  dining_room: boolean
  garage: boolean
  style: 'modern' | 'traditional' | 'minimalist' | 'colonial' | 'contemporary'
  floors: number
  outdoor_features: string[]
  special_rooms: string[]
  additional_notes: string
}

export async function triggerFloorPlanGeneration(
  job_id: string,
  user_requirements: UserRequirements,
): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${BASE}/api/generate-floorplans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id, user_requirements }),
  })
  return handleResponse(res)
}

export async function pollFloorPlanStatus(
  job_id: string,
): Promise<{ status: string; alternatives: FloorPlanAlternative[] | null }> {
  const res = await fetch(`${BASE}/api/floorplans/status/${job_id}`)
  return handleResponse(res)
}

export async function selectPlan(
  job_id: string,
  variant: string,
): Promise<FullDesignPackage> {
  const res = await fetch(`${BASE}/api/select-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id, selected_variant: variant }),
  })
  return handleResponse(res)
}

export async function generateVideo(job_id: string): Promise<VideoAsset> {
  const res = await fetch(`${BASE}/api/generate-video`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id }),
  })
  return handleResponse(res)
}
