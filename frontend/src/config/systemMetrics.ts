/**
 * NGUỒN SỐ LIỆU THỐNG NHẤT VÀ XÁC THỰC (SINGLE SOURCE OF TRUTH)
 * VietIRR-RAG — Đồng bộ số liệu toàn diện giữa Trang chủ, Không gian Tra cứu,
 * Báo cáo Khoa học và Chế độ Báo cáo Hội đồng.
 * 
 * Ngày kiểm toán: 30/10/2026
 * Mọi số liệu đều có căn cứ từ artifact manifest và báo cáo thực nghiệm đóng băng.
 */

export interface CorpusMetadata {
  version: string
  name: string
  status: 'OPERATIONAL' | 'FROZEN_BASELINE'
  documentCount: number
  pageCount: number
  evidenceUnitCount: number
  textRegionCount: number
  tableRegionCount: number
  tableCount?: number
  qaTotal?: number
  qaCore?: number
  qaChallenge?: number
  retrievalPipeline: string
  sourceAgencies: string[]
  verifiedAt: string
}

export interface RetrievalMetric {
  name: string
  metricKey: string
  value: string
  rawRate: number
  fraction: string
  cohort: string
  stage: string
  artifactSource: string
  description: string
}

/**
 * 1. CORPUS HIỆN HÀNH ĐANG VẬN HÀNH TRÊN HỆ THỐNG (V4_R6_FROZEN)
 * Nguồn: data/v4_corpus/metadata/v4_corpus_manifest.jsonl
 *        outputs/V4_EXPERIMENT/index/pages_v4.jsonl (2.578 trang)
 *        outputs/V4_EXPERIMENT/index/evidence_units_v4.jsonl (27.144 đơn vị)
 */
export const OPERATIONAL_CORPUS_V4: CorpusMetadata = {
  version: 'V4_R6_FROZEN',
  name: 'V4 Canonical Frozen Corpus',
  status: 'OPERATIONAL',
  documentCount: 93,
  pageCount: 2578,
  evidenceUnitCount: 27144,
  textRegionCount: 27053,
  tableRegionCount: 91,
  retrievalPipeline: 'R6 Hybrid (Dual BM25 + Dense BGE-M3 + Reranker BGE-v2-m3 + Budget B: 5 units)',
  sourceAgencies: [
    'Cục Quản lý và Xây dựng công trình thủy lợi (Cục Thủy lợi)',
    'Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)',
    'Thủ tướng Chính phủ (Quy trình vận hành liên hồ chứa)',
    'Bộ Nông nghiệp và Phát triển nông thôn',
  ],
  verifiedAt: '2026-10-30',
}

/**
 * 2. CORPUS VÀ METRIC BASELINE LỊCH SỬ (V3.2_FINAL_SEMANTIC)
 * Nguồn: reports/v3_2_final_semantic/dataset_stats.json & vietirr.db
 *        reports/B2/B2_BASELINE_METRICS.json
 */
export const BASELINE_CORPUS_V3: CorpusMetadata = {
  version: 'V3.2_FINAL_SEMANTIC',
  name: 'V3.2 Frozen Semantic Baseline',
  status: 'FROZEN_BASELINE',
  documentCount: 89,
  pageCount: 2479,
  evidenceUnitCount: 27045,
  textRegionCount: 26954,
  tableRegionCount: 91,
  tableCount: 406,
  qaTotal: 545,
  qaCore: 378,
  qaChallenge: 167,
  retrievalPipeline: 'BM25_B1_FROZEN_CORPUS / Windowed Routing (Stage P2)',
  sourceAgencies: [
    'Cục Thủy lợi — Bộ NN&PTNT',
    'Viện Quy hoạch Thủy lợi Miền Nam (SIWRP)',
  ],
  verifiedAt: '2026-10-16',
}

/**
 * 3. BẢNG CHỈ SỐ RETRIEVAL R6 ĐƯỢC XÁC NHẬN TRÊN TẬP DEV-93
 * Nguồn: research/r6_1b_window_allocation/reports/01_BASELINE_AND_EXPERIMENT_CONTRACT.md
 *        research/r6_1b_window_allocation/reports/08_FULL_DEV93_COMPARISON.md
 */
export const VERIFIED_R6_METRICS: RetrievalMetric[] = [
  {
    name: 'Candidate Hit@100',
    metricKey: 'candidate_hit_100',
    value: '91,40%',
    rawRate: 0.9140,
    fraction: '85 / 93',
    cohort: 'DEV-93 (93 câu hỏi kiểm nghiệm độc lập)',
    stage: 'R6 Frozen Baseline',
    artifactSource: 'research/r6_1b_window_allocation/reports/01_BASELINE_AND_EXPERIMENT_CONTRACT.md',
    description: 'Tỷ lệ câu hỏi mà trang chứa bằng chứng chuẩn (gold) nằm trong Top 100 ứng viên ban đầu.',
  },
  {
    name: 'Page Hit@5',
    metricKey: 'page_hit_5',
    value: '67,74%',
    rawRate: 0.6774,
    fraction: '63 / 93',
    cohort: 'DEV-93 (93 câu hỏi kiểm nghiệm độc lập)',
    stage: 'R6 Frozen Baseline (Budget B)',
    artifactSource: 'research/r6_1b_window_allocation/reports/08_FULL_DEV93_COMPARISON.md',
    description: 'Tỷ lệ câu hỏi mà trang chứa bằng chứng chuẩn nằm trong Top 5 trang xuất sắc nhất.',
  },
  {
    name: 'Evidence Page Hit@5',
    metricKey: 'evidence_page_hit_5',
    value: '61,29%',
    rawRate: 0.6129,
    fraction: '57 / 93',
    cohort: 'DEV-93 (93 câu hỏi kiểm nghiệm độc lập)',
    stage: 'R6 Frozen Baseline (Budget B)',
    artifactSource: 'research/r6_1b_window_allocation/reports/08_FULL_DEV93_COMPARISON.md',
    description: 'Tỷ lệ câu hỏi mà vùng bằng chứng chính xác tuyệt đối được đưa vào ngữ cảnh sinh câu trả lời.',
  },
  {
    name: 'MRR (Mean Reciprocal Rank)',
    metricKey: 'mrr',
    value: '0.4516',
    rawRate: 0.4516,
    fraction: '—',
    cohort: 'DEV-93',
    stage: 'R6 Frozen Baseline',
    artifactSource: 'research/r6_1b_window_allocation/reports/01_BASELINE_AND_EXPERIMENT_CONTRACT.md',
    description: 'Thứ hạng nghịch đảo trung bình của bằng chứng chuẩn đầu tiên.',
  },
  {
    name: 'nDCG@10',
    metricKey: 'ndcg_10',
    value: '0.5082',
    rawRate: 0.5082,
    fraction: '—',
    cohort: 'DEV-93',
    stage: 'R6 Frozen Baseline',
    artifactSource: 'research/r6_1b_window_allocation/reports/01_BASELINE_AND_EXPERIMENT_CONTRACT.md',
    description: 'Điểm xếp hạng Normalized Discounted Cumulative Gain tại Top 10.',
  },
  {
    name: 'Rò rỉ phân tách (Family Leakage)',
    metricKey: 'data_leakage',
    value: '0.00%',
    rawRate: 0.00,
    fraction: '0 / 93 trùng họ tài liệu',
    cohort: 'Train-Dev Strict Isolation',
    stage: 'Split & Leakage Protocol',
    artifactSource: 'V4_SPLIT_LEAKAGE_PROTOCOL.md & tests/test_gold_leakage_adversarial.py',
    description: 'Khóa phân tách tuyệt đối: không có văn bản hoặc họ văn bản (document family) nào trong DEV xuất hiện trong tập Train; prompt thời gian thực không chứa đáp án chuẩn.',
  },
]

/**
 * 4. THÔNG TIN CÔNG NGHỆ VÀ MÔ HÌNH THỜI GIAN THỰC
 */
export const SYSTEM_RUNTIME_CONFIG = {
  retrievalEngine: 'R6 Hybrid (BM25 + BGE-M3 + BGE-Reranker-v2-m3)',
  generationModel: 'Qwen2.5:7B (Ollama Local GPU)',
  citationGuard: 'Rule-based Atomic Claim & Numeric Grounding Guard',
  ontologyVerificationMode: 'Shadow Mode (Quan trắc không can thiệp E1)',
  pdfViewerServing: 'Tích hợp mở PDF trực tiếp theo số trang (/api/v1/documents/{doc_id}/pdf?page={p})',
  hardwareDeployment: 'NVIDIA GPU 16 GB VRAM, Local In-house Inference (Không dùng API trả phí)',
}
