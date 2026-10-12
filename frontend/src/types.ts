export type ServiceStatus = {
  status: 'ready' | string
  service: string
  mode: 'EVIDENCE_SEARCH'
  answer_generation: boolean
  retrieval_method: string
  corpus_version: string
  index_cache: string
  evidence_units: number
  uptime_seconds: number
}

export type CorpusStats = {
  corpus_version: string
  frozen: boolean
  human_validated: boolean
  documents: number
  pages: number
  regions: number
  tables: number
  evidence_units: number
  qa_total: number
  qa_core: number
  qa_challenge: number
  source_grounded_negatives: number
  retrieval_method: string
}

export type Evidence = {
  evidence_id: string
  doc_id: string
  page_id: string
  page_number: number
  unit_type: 'TEXT_REGION' | 'TABLE_REGION' | string
  score: number
  rank: number
  relevance: number
  text: string
  title: string
  source_agency: string
  source_url?: string
  doc_type: string
  pdf_available: boolean
  pdf_url?: string
}

export type SearchResponse = {
  query: string
  mode: 'EVIDENCE_SEARCH'
  answer: null
  answer_notice: string
  retrieval_method: string
  result_count: number
  latency_ms: number
  results: Evidence[]
}

export type DocumentRecord = {
  doc_id: string
  title: string
  doc_type: string
  source_agency: string
  source_domain?: string
  source_url?: string
  publication_date?: string
  page_count?: number
  core_or_temporal?: string
  basin: string[]
  province: string[]
  acceptance_status?: string
  redistribution_status?: string
  pdf_available: boolean
  pdf_url?: string
  document_number?: string
  effective_date?: string
  landing_page_url?: string
  version_status?: string
  is_scanned?: boolean
  ocr_used?: boolean
  human_validated?: boolean
  evidence_count?: number
  regions?: Array<{
    evidence_id: string
    page_number: number
    unit_type: string
    text: string
  }>
}

export type DocumentListResponse = {
  items: DocumentRecord[]
  total: number
  page: number
  page_size: number
  types: string[]
}
