import type { CorpusStats, DocumentListResponse, DocumentRecord, SearchResponse, ServiceStatus } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const data = await response.json().catch(() => ({ error: 'Phản hồi dịch vụ không hợp lệ.' }))
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)
  return data as T
}

export const api = {
  health: () => request<ServiceStatus>('/api/health'),
  stats: () => request<CorpusStats>('/api/stats'),
  search: (query: string, topK = 8) => request<SearchResponse>('/api/search', {
    method: 'POST',
    body: JSON.stringify({ query, top_k: topK }),
  }),
  documents: (query = '', type = '') => {
    const params = new URLSearchParams({ page_size: '100' })
    if (query) params.set('q', query)
    if (type) params.set('type', type)
    return request<DocumentListResponse>(`/api/documents?${params}`)
  },
  document: (docId: string) => request<DocumentRecord>(`/api/documents/${encodeURIComponent(docId)}`),
  absoluteUrl: (path?: string) => path ? `${API_BASE}${path}` : undefined,
}
