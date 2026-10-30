import { ChevronRight, Cpu, Layers } from 'lucide-react'
import { useState } from 'react'

interface ArchStage {
  id: string
  step: string
  title: string
  tech: string
  summary: string
  specs: string[]
}

const ARCH_STAGES: ArchStage[] = [
  {
    id: 'ingest',
    step: '01',
    title: 'Tiền Xử Lý & Trích Xuất Cấu Trúc',
    tech: 'PyMuPDF + Canonical OCR Parser',
    summary: 'Chuyển hóa 93 file PDF chính thống thành 27.144 evidence units gồm 27.053 text regions và 91 structured tables.',
    specs: [
      'Phát hiện bảng biểu tự động & bảo toàn quan hệ hàng - cột',
      'Định danh mã băm SHA-256 từng trang & toàn bộ tài liệu',
      'Gắn thẻ phân loại: TEXT_REGION vs TABLE_REGION',
    ],
  },
  {
    id: 'window',
    step: '02',
    title: 'Phân Đoạn Cửa Sổ Trượt (Windowing)',
    tech: 'Sliding Spans (384 / Overlap 128)',
    summary: 'Giải quyết triệt để điểm nghẽn giới hạn 512 tokens của các mô hình Dense, hạ tỷ lệ cắt ngắn từ 66% xuống 0%.',
    specs: [
      'Content tokens: 384 tokens mỗi cửa sổ',
      'Overlap: 128 tokens để không mất ngữ cảnh giáp ranh',
      'Window aggregation: Max-pooling về Evidence ID gốc',
    ],
  },
  {
    id: 'retrievers',
    step: '03',
    title: 'Truy Xuất Song Song (Dual-Stream)',
    tech: 'Rank-BM25 + BGE-M3 (Dual-Stream)',
    summary: 'Kết hợp sức mạnh tìm kiếm từ khóa chính xác (BM25) và ngữ nghĩa sâu (Dense vector 1024 chiều).',
    specs: [
      'BM25: k1=1.5, b=0.75, Unicode NFC tokenizer tiếng Việt',
      'Dense Encoder: BAAI/bge-m3 (1024-dim, L2-normalized)',
      'Index cache: Binary .pkl và .npy lưu trữ cục bộ',
    ],
  },
  {
    id: 'fusion',
    step: '04',
    title: 'Hợp Nhất Hạng RRF & BGE Reranker',
    tech: 'RRF (k=60) + BGE-Reranker-Large',
    summary: 'Thu thập Top-100 ứng viên đa nguồn và tái xếp hạng Top-20 chính xác cao bằng Cross-Encoder.',
    specs: [
      'Công thức RRF: RRF(d) = ∑ 1 / (60 + rank_m(d))',
      'Cross-Encoder: bge-reranker-large chấm điểm câu hỏi và đoạn trích',
      'Candidate Hit@100 đạt 91,40% trên DEV-93',
    ],
  },
  {
    id: 'routing',
    step: '05',
    title: 'Định Tuyến Phân Tầng Page→Region',
    tech: 'Budget B=5 Evidence Selection',
    summary: 'Lọc trang tiềm năng nhất trước, sau đó chọn tối đa 5 đơn vị bằng chứng quan trọng nhất đưa vào ngữ cảnh LLM.',
    specs: [
      'Giảm không gian tìm kiếm từ 27.144 vùng xuống Top-5 vùng tối ưu',
      'Page Hit@5 đạt 67,74% và Evidence Page Hit@5 đạt 61,29%',
      'Cấu trúc hóa bảng biểu kèm tiêu đề văn bản',
    ],
  },
  {
    id: 'provenance',
    step: '06',
    title: 'Sinh Trả Lời & Citation Guard',
    tech: 'Qwen2.5:7B + Citation Guard + PDF Viewer',
    summary: 'LLM sinh câu trả lời có đối chiếu token nguyên văn; Citation Guard chặn hoàn toàn hallucination và mở PDF Viewer đúng trang.',
    specs: [
      'Mô hình sinh: Qwen2.5:7B-Instruct chạy GPU nội bộ',
      'Citation Guard: Bắt buộc 100% số liệu và thực thể có mặt trong ngữ cảnh',
      'PDF Viewer nhúng mở tức thì tài liệu gốc tại đúng số trang',
    ],
  },
]

export function Scene04Architecture() {
  const [activeStage, setActiveStage] = useState<ArchStage>(ARCH_STAGES[4]) // Stage 05 default

  return (
    <div className="clean-slide-container scene-architecture">
      <div className="slide-header-block">
        <span className="slide-chapter-tag font-mono">SCENE 04 · KIẾN TRÚC HỆ THỐNG</span>
        <h2 className="slide-main-heading">Pipeline Đa Tầng Của VietIrr-RAG</h2>
        <p className="slide-sub-heading">
          Từ văn bản PDF thô đến bằng chứng được trích dẫn có kiểm chứng. Nhấn vào từng giai đoạn để xem thông số kỹ thuật chi tiết.
        </p>
      </div>

      {/* Clean Linear Stepper */}
      <div className="clean-arch-stepper">
        {ARCH_STAGES.map((stage) => {
          const isSelected = activeStage.id === stage.id
          return (
            <button
              key={stage.id}
              type="button"
              className={`clean-stepper-tab ${isSelected ? 'is-active' : ''}`}
              onClick={() => setActiveStage(stage)}
            >
              <span className="stepper-tab-num font-mono">{stage.step}</span>
              <span className="stepper-tab-title">{stage.title}</span>
            </button>
          )
        })}
      </div>

      {/* Focused Detail Container */}
      <div className="clean-stage-detail-box">
        <div className="detail-top-meta">
          <div>
            <span className="detail-stage-num font-mono">GIAI ĐOẠN {activeStage.step}</span>
            <h3 className="detail-stage-title">{activeStage.title}</h3>
          </div>
          <span className="detail-tech-badge font-mono">{activeStage.tech}</span>
        </div>

        <p className="detail-summary-text">{activeStage.summary}</p>

        <div className="detail-specs-grid">
          {activeStage.specs.map((spec, idx) => (
            <div key={idx} className="spec-item">
              <span className="spec-indicator" />
              <span>{spec}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
