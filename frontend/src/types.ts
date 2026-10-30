export type StageStatus = 'completed' | 'in_progress' | 'blocked' | 'planned'

export interface ServiceStatus {
  status: 'ready' | 'degraded'
  service: string
  api_version: string
  mode: string
  answer_generation: boolean
  retrieval_method: string
  corpus_version: string
  index_cache: string
  evidence_units: number
  database: 'ready' | 'unavailable'
  public_mode: boolean
  uptime_seconds: number
}

export interface CorpusStats {
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
  verified_at: string | null
}

export interface ProjectStage {
  id: string
  order_index: number
  name: string
  status: StageStatus
  summary: string
  evidence_source: string
  updated_at: string
}

export interface StagesResponse {
  items: ProjectStage[]
  source: string
  updated_at: string | null
}

export interface Evidence {
  rank: number
  evidence_id: string
  doc_id: string
  page_number: number
  unit_type: string
  score: number
  relevance: number
  text: string | null
  title: string
  source_agency: string
  source_url?: string
  doc_type: string
  redistribution_status: string
  pdf_available: boolean
  pdf_url?: string
  access_notice?: string
}

export interface SearchResponse {
  query: string
  mode: string
  answer: null
  answer_notice: string
  retrieval_method: string
  corpus_version: string
  result_count: number
  latency_ms: number
  excerpt_policy: 'local_research' | 'approved_public_only' | 'metadata_only'
  results: Evidence[]
}

export interface QACitation {
  document_id: string
  page_id: string
  page_number: number
  evidence_id: string
  source_version: string
  snippet: string
  provenance_status: 'VALID' | 'PDF_UNAVAILABLE'
  viewer_url?: string
  title: string
  source_agency: string
  unit_type: string
}

export interface QAResponse {
  request_id: string
  answer: string
  pipeline: 'r6'
  generation_model: string
  corpus_version: string
  verification: { mode: string; status: string }
  correction: { mode: string; status: string }
  citations: QACitation[]
  retrieved_references?: QACitation[]
  timing_ms: Record<string, number | null>
  trace: Record<string, unknown>
  abstained?: boolean
  abstention_type?: 'NONE' | 'MODEL_ABSTAINED' | 'GUARD_REJECTED' | 'NO_PERMITTED_EVIDENCE' | 'NO_EVIDENCE'
  guard_verdict?: 'PASS' | 'ABSTAIN' | 'NOT_RUN'
  guard_reason?: string
  model_generated_answer?: boolean
  final_status?: 'FINAL_ANSWER_ACCEPTED' | 'FINAL_ABSTAINED'
}

export interface DocumentRegion {
  evidence_id: string
  page_number: number
  unit_type: string
  text: string | null
}

export interface DocumentRecord {
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
  redistribution_status: string
  pdf_available: boolean
  pdf_url?: string
  evidence_count?: number
  regions?: DocumentRegion[]
  access_notice?: string
}

export interface DocumentListResponse {
  items: DocumentRecord[]
  total: number
  page: number
  page_size: number
  pages: number
  types: string[]
}

export interface MetricValues {
  sample_count: number
  '5': { any_recall: number; all_recall: number; gold_coverage: number }
  '10': { any_recall: number; all_recall: number; gold_coverage: number }
  '20': { any_recall: number; all_recall: number; gold_coverage: number }
  mrr: number
  'ndcg@10': number
}

export interface ReportMilestone {
  slug: string
  title: string
  summary: string
  status: StageStatus
  occurred_on: string | null
  source_path: string
}

export interface ReportResponse {
  generated_at: string | null
  sources: string[]
  corpus: {
    v3_2: CorpusStats
    v4_4: Record<string, unknown>
  }
  datasets: {
    v3_2_frozen: { counts: Record<string, number>; candidate_test: string; evaluation_scope_used_now: string }
    v4_pre_expansion_registry: Record<string, unknown>
    v4_candidate_expansion: {
      records_total: number
      after_all_quarantine: number
      normalized_status_counts: Record<string, number>
      human_gold_true: number
      unique_source_documents: number
      source_files_are_local_only: boolean
    }
  }
  data_quality: {
    candidate_evidence_instances: number
    candidate_evidence_page_locators: number
    candidate_evidence_without_anchor_claim_or_locator: number
    review_flags_nonempty_records: number
    evaluation_eligible_v4_candidates: number
    evaluation_exclusion_reason: string
  }
  retrieval: {
    scope: string
    mode: string
    qa_evaluated: number
    metrics: Record<string, MetricValues>
    live_method: string
    demo_queries: Array<Record<string, unknown>>
  }
  limitations: string[]
  milestones: ReportMilestone[]
}
