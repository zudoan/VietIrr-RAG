import type {
  CorpusStats,
  DocumentListResponse,
  DocumentRecord,
  ReportResponse,
  QAResponse,
  SearchResponse,
  ServiceStatus,
  StagesResponse,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit, timeoutMs = 15_000): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
    })
    const data = await response.json().catch(() => ({ detail: 'Phản hồi dịch vụ không hợp lệ.' }))
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`)
    return data as T
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') {
      throw new Error('Dịch vụ phản hồi quá thời gian cho phép.')
    }
    throw reason
  } finally {
    window.clearTimeout(timeout)
  }
}

export const api = {
  health: () => request<ServiceStatus>('/api/v1/health'),
  stats: () => request<CorpusStats>('/api/v1/stats'),
  stages: () => request<StagesResponse>('/api/v1/stages'),
  report: () => request<ReportResponse>('/api/v1/report'),
  search: (query: string, topK = 8) => request<SearchResponse>('/api/v1/search', {
    method: 'POST',
    body: JSON.stringify({ query, top_k: topK }),
  }),
  ask: (question: string) => request<QAResponse>('/api/v1/qa', {
    method: 'POST',
    body: JSON.stringify({ question, pipeline: 'r6', verification_mode: 'off', correction_mode: 'off' }),
  }, 180_000),
  documents: (query = '', type = '', page = 1) => {
    const params = new URLSearchParams({ page: String(page), page_size: '24' })
    if (query) params.set('q', query)
    if (type) params.set('type', type)
    return request<DocumentListResponse>(`/api/v1/documents?${params}`)
  },
  document: (docId: string) => request<DocumentRecord>(`/api/v1/documents/${encodeURIComponent(docId)}`),
  absoluteUrl: (path?: string) => path ? `${API_BASE}${path}` : undefined,
}
