import { requestJson, requestFormData } from '../../../shared/api/http'
import type { ResumeDraft, ResumeResponse } from '../model/types'

const RESUME_API = '/api/resume'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export function getResume(): Promise<ResumeResponse> {
  return requestJson<ResumeResponse>(RESUME_API)
}

export function saveResume(draft: ResumeDraft): Promise<ResumeResponse> {
  return requestJson<ResumeResponse>(RESUME_API, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft),
  })
}

export async function uploadResumePhoto(file: File): Promise<{ photo_id: string }> {
  const formData = new FormData()
  formData.append('file', file)
  return requestFormData<{ photo_id: string }>(`${RESUME_API}/photo`, formData)
}

export function deleteStagedResumePhoto(photoId: string): Promise<{ photo_id: string; deleted: boolean }> {
  return requestJson(`${RESUME_API}/photo?photo_id=${encodeURIComponent(photoId)}`, {
    method: 'DELETE',
  })
}

export async function getSavedResumePhoto(): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${RESUME_API}/photo`, {
    credentials: 'same-origin',
    headers: { Accept: 'image/png, image/jpeg' },
  })
  notifySessionExpired(response.status)
  if (!response.ok) throw new Error(await readErrorMessage(response))
  return response.blob()
}

export async function downloadResumePdf(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${RESUME_API}/export/pdf`, {
    credentials: 'same-origin',
    headers: { Accept: 'application/pdf' },
  })
  notifySessionExpired(response.status)
  if (!response.ok) throw new Error(await readErrorMessage(response))

  const objectUrl = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = 'resume.pdf'
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000)
}

function notifySessionExpired(status: number): void {
  if (status === 401) window.dispatchEvent(new Event('nexusai:unauthenticated'))
}

async function readErrorMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as {
    message?: unknown
    detail?: unknown
  } | null
  if (typeof body?.message === 'string') return body.message
  if (typeof body?.detail === 'string') return body.detail
  return `请求失败（HTTP ${response.status}）`
}
