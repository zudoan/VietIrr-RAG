import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Award,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Database,
  ExternalLink,
  EyeOff,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  Filter,
  Flag,
  GraduationCap,
  Layers,
  MapPin,
  Maximize2,
  Play,
  RotateCcw,
  Scale,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Split,
  TrendingUp,
  Trophy,
  Users,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  BASELINE_CORPUS_V3,
  OPERATIONAL_CORPUS_V4,
  SYSTEM_RUNTIME_CONFIG,
  VERIFIED_R6_METRICS,
} from '../../config/systemMetrics'

interface PipelineStep {
  id: string
  num: string
  title: string
  tech: string
  summary: string
  specs: string[]
}

const PIPELINE_STEPS: PipelineStep[] = [
  {
    id: 'step-1',
    num: '01',
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
    id: 'step-2',
    num: '02',
    title: 'Phân Đoạn Cửa Sổ Trượt (Sliding Spans)',
    tech: 'Windowing (384 tokens / Overlap 128)',
    summary: 'Giải quyết triệt để điểm nghẽn giới hạn 512 tokens của các mô hình Dense, hạ tỷ lệ cắt ngắn từ 66% xuống 0%.',
    specs: [
      'Content tokens: 384 tokens mỗi cửa sổ',
      'Overlap: 128 tokens để không mất ngữ cảnh giáp ranh',
      'Window aggregation: Max-pooling về Evidence ID gốc',
    ],
  },
  {
    id: 'step-3',
    num: '03',
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
    id: 'step-4',
    num: '04',
    title: 'Hợp Nhất Hạng RRF (Fusion)',
    tech: 'Reciprocal Rank Fusion (k=60)',
    summary: 'Tổng hợp danh sách xếp hạng từ hai mô hình độc lập mà không cần chuẩn hóa phân phối điểm số.',
    specs: [
      'Công thức: RRF(d) = ∑ 1 / (60 + rank_m(d))',
      'Tie-breaking xác định: Ưu tiên điểm cao, sau đó Evidence ID',
      'Ngăn chặn hiện tượng một mô hình áp đảo tuyệt đối',
    ],
  },
  {
    id: 'step-5',
    num: '05',
    title: 'Định Tuyến Phân Tầng Page→Region',
    tech: 'P2 Controlled Page Routing',
    summary: 'Lọc Top-P trang tiềm năng nhất trước, sau đó mới rank các vùng trong trang để tối ưu AllRecall@20.',
    specs: [
      'Giảm không gian tìm kiếm từ 27.045 vùng xuống vài chục vùng',
      'Đột phá P2: Nâng Complete-page Recall@20 lên 0.742',
      'Loại bỏ nhiễu từ các văn bản không liên quan',
    ],
  },
  {
    id: 'step-6',
    num: '06',
    title: 'Xuất Bằng Chứng & Thẩm Định Nguồn',
    tech: 'FastAPI Service + In-App PDF Viewer',
    summary: 'Trả về Top-K bằng chứng có số trang chính xác, trích dẫn chuẩn khoa học và xem trực tiếp PDF ngay trong web.',
    specs: [
      'Độ trễ trung bình: ~3,9 ms (BM25 cache hit)',
      'Không sử dụng câu trả lời sinh tự do (Non-generative)',
      'Đảm bảo 100% tính kiểm chứng trước hội đồng',
    ],
  },
]

const REPORT_CHAPTERS = [
  { id: 'sec-intro', label: '01 · Mở Đầu' },
  { id: 'sec-context', label: '02 · Bối Cảnh' },
  { id: 'sec-problem', label: '03 · Thách Thức' },
  { id: 'sec-solution', label: '04 · Giải Pháp' },
  { id: 'sec-architecture', label: '05 · Kiến Trúc' },
  { id: 'sec-pipeline', label: '06 · Pipeline' },
  { id: 'sec-demo', label: '07 · Trình Diễn' },
  { id: 'sec-methodology', label: '08 · Phương Pháp' },
  { id: 'sec-evaluation', label: '09 · Thực Nghiệm' },
  { id: 'sec-conclusion', label: '10 · Tổng Kết' },
]

export function ScientificScrollReport() {
  const navigate = useNavigate()
  const [activeStepId, setActiveStepId] = useState<string>('step-1')
  const [activeChapterId, setActiveChapterId] = useState<string>('sec-intro')
  const [scrollProgress, setScrollProgress] = useState<number>(0)
  const [activeEvalTab, setActiveEvalTab] = useState<'r6' | 'p2' | 'b2' | 'negative'>('r6')

  // Track scroll progress and active chapter
  useEffect(() => {
    const handleScroll = () => {
      const totalHeight = document.documentElement.scrollHeight - window.innerHeight
      if (totalHeight > 0) {
        const progress = Math.min(100, Math.max(0, (window.scrollY / totalHeight) * 100))
        setScrollProgress(progress)
      }

      // Check active chapter via element viewport offset
      for (let i = REPORT_CHAPTERS.length - 1; i >= 0; i--) {
        const el = document.getElementById(REPORT_CHAPTERS[i].id)
        if (el) {
          const rect = el.getBoundingClientRect()
          if (rect.top <= 240) {
            setActiveChapterId(REPORT_CHAPTERS[i].id)
            break
          }
        }
      }
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll()
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const handleScrollToChapter = (id: string) => {
    const el = document.getElementById(id)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
    }
  }

  const handleLaunchWorkspace = (query?: string) => {
    const qParam = query ? `?q=${encodeURIComponent(query)}` : ''
    navigate(`/app${qParam}`)
  }

  return (
    <div className="scientific-report-root">
      {/* ─── Top Reading Progress Indicator ─── */}
      <div
        className="reading-progress-bar"
        style={{ width: `${scrollProgress}%` }}
        aria-hidden="true"
      />

      {/* ─── Sticky Chapter Navigation Bar ─── */}
      <nav className="sticky-chapter-nav" aria-label="Mục lục báo cáo khoa học">
        <div className="chapter-nav-inner">
          <div className="nav-brand-group">
            <Link to="/app" className="nav-brand-link">
              <span className="brand-dot" />
              <strong>VietIrr-RAG</strong>
            </Link>
            <span className="nav-divider">/</span>
            <span className="nav-report-title">Báo Cáo Nghiên Cứu Khoa Học</span>
          </div>

          <div className="chapter-links-scroll">
            {REPORT_CHAPTERS.map((ch) => (
              <button
                key={ch.id}
                type="button"
                className={`chapter-link-btn ${activeChapterId === ch.id ? 'is-active' : ''}`}
                onClick={() => handleScrollToChapter(ch.id)}
              >
                {ch.label}
              </button>
            ))}
          </div>

          <div className="nav-action-group">
            <button
              type="button"
              className="btn-nav-launch"
              onClick={() => handleLaunchWorkspace()}
            >
              <Play size={13} />
              <span>Mở RAG Workspace</span>
            </button>
          </div>
        </div>
      </nav>

      <main className="report-main-flow">
        {/* ==================================================================
            SECTION 01: INTRODUCTION
            ================================================================== */}
        <section id="sec-intro" className="report-section section-intro">
          <div className="section-container">
            <div className="academic-badge-row">
              <span className="inst-tag font-mono">
                <GraduationCap size={15} />
                <span>TRƯỜNG ĐẠI HỌC THỦY LỢI (TLU) · KHOA CÔNG NGHỆ THÔNG TIN</span>
              </span>
              <span className="inst-sub font-mono">ĐỒ ÁN NGHIÊN CỨU HỌC SÂU & RAG HỆ THỐNG (2026)</span>
            </div>

            <div className="intro-hero-block">
              <span className="intro-kicker font-mono">VIETIRR-RAG · RESEARCH MONOGRAPH & BENCHMARK</span>
              <h1 className="intro-main-title">
                Truy xuất bằng chứng kỹ thuật<br />
                từ tài liệu thủy lợi tiếng Việt dài.
              </h1>
              <p className="intro-lead-text">
                Nghiên cứu kiến trúc Evidence-First Retrieval có thẩm định nguồn gốc (Provenance-Centric)
                cho các văn bản pháp quy, báo cáo quy hoạch lưu vực sông và số liệu quan trắc hồ chứa - đập dâng,
                bảo đảm mỗi kết luận kỹ thuật đều có bằng chứng số trang và file PDF đối chiếu trực tiếp.
              </p>
            </div>

            <div className="intro-authors-grid">
              <div className="author-card">
                <div className="author-head">
                  <Users size={16} className="text-teal" />
                  <span className="author-role">Sinh viên thực hiện</span>
                </div>
                <strong className="author-name">Nhóm Nghiên cứu VietIrr-RAG</strong>
                <span className="author-meta">Chuyên ngành Khoa học Dữ liệu & Trí tuệ Nhân tạo</span>
              </div>

              <div className="author-card">
                <div className="author-head">
                  <Award size={16} className="text-teal" />
                  <span className="author-role">Đơn vị chuyên môn</span>
                </div>
                <strong className="author-name">Bộ môn Học sâu & Xử lý Ngôn ngữ Tự nhiên</strong>
                <span className="author-meta">Khoa CNTT — Trường Đại học Thủy Lợi</span>
              </div>

              <div className="author-card">
                <div className="author-head">
                  <ShieldCheck size={16} className="text-teal" />
                  <span className="author-role">Trọng tâm học thuật</span>
                </div>
                <strong className="author-name">Evidence-First vs Hallucination</strong>
                <span className="author-meta">Đo lường Complete-Evidence Recall (AllRecall@K)</span>
              </div>
            </div>

            <div className="intro-stats-strip">
              <div className="stat-pill">
                <span className="stat-val font-mono">{OPERATIONAL_CORPUS_V4.documentCount}</span>
                <span className="stat-label">PDFs Chính Thống (V4)</span>
              </div>
              <div className="stat-pill">
                <span className="stat-val font-mono">{OPERATIONAL_CORPUS_V4.evidenceUnitCount.toLocaleString('vi-VN')}</span>
                <span className="stat-label">Đơn vị bằng chứng</span>
              </div>
              <div className="stat-pill">
                <span className="stat-val font-mono highlight">91.40%</span>
                <span className="stat-label">R6 Hit@100 (DEV-93)</span>
              </div>
              <div className="stat-pill">
                <span className="stat-val font-mono highlight">67.74%</span>
                <span className="stat-label">R6 Page Hit@5</span>
              </div>
              <div className="stat-pill">
                <span className="stat-val font-mono good">0.00%</span>
                <span className="stat-label">Rò rỉ phân tách (Leakage)</span>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 02: RESEARCH CONTEXT
            ================================================================== */}
        <section id="sec-context" className="report-section section-context">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 02 · BỐI CẢNH NGHIÊN CỨU</span>
              <h2 className="section-title">Thực Trạng Khai Thác Tri Thức Ngành Thủy Lợi Việt Nam</h2>
              <p className="section-subtitle">
                Tại sao các giải pháp RAG tổng quát (Generic RAG) trong thương mại điện tử hay tài chính
                không thể đáp ứng được yêu cầu khắt khe của văn bản kỹ thuật công trình nước?
              </p>
            </div>

            <div className="context-editorial-grid">
              <div className="context-column">
                <h3 className="column-title">1. Tính Đa Dạng & Khối Lượng Tài Liệu Quy Hoạch</h3>
                <p>
                  Ngành Thủy lợi Việt Nam quản lý hơn 7.000 hồ chứa thủy lợi và hàng trăm hệ thống đê điều,
                  kênh mương đầu mối. Các văn bản quy hoạch lưu vực (như sông Hồng - Thái Bình, sông Mã,
                  sông Vu Gia - Thu Bồn, Đồng bằng Sông Cửu Long) thường có độ dài từ 50 đến hơn 300 trang.
                </p>
                <p>
                  Các tài liệu này bao gồm các thông tư quy chuẩn kỹ thuật (TCVN), quy trình vận hành liên hồ chứa,
                  và bản tin dự báo nguồn nước định kỳ được ban hành bởi Cục Thủy Lợi và Viện Quy hoạch Thủy lợi Miền Nam (SIWRP).
                </p>
              </div>

              <div className="context-column">
                <h3 className="column-title">2. Yêu Cầu Nghiêm Ngặt Về Thẩm Định Nguồn Gốc (Provenance)</h3>
                <p>
                  Trong thủy lợi, một câu trả lời kỹ thuật không có số trang và chữ ký nguồn gốc là một câu trả lời
                  <strong>không thể sử dụng trong thực tế</strong>. Nếu mô hình AI tổng hợp nhầm số liệu dung tích phòng lũ
                  giữa hai hồ chứa khác nhau hoặc nhầm lẫn đơn vị (m³ so với triệu m³), hậu quả điều hành xả lũ có thể dẫn đến rủi ro thảm họa.
                </p>
                <p>
                  Do đó, dự án đặt ra nguyên tắc cốt lõi: <em>Provenance-First</em> — mọi thông tin đưa ra phải mở được
                  chính xác trang tài liệu PDF gốc kèm chứng chỉ toàn vẹn dữ liệu SHA-256.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 03: RESEARCH PROBLEM
            ================================================================== */}
        <section id="sec-problem" className="report-section section-problem">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 03 · BÀI TOÁN & THÁCH THỨC</span>
              <h2 className="section-title">Ba Điểm Nghẽn Kỹ Thuật Đã Được Nhận Diện</h2>
              <p className="section-subtitle">
                Phân tích các giới hạn nội tại của mô hình Transformer tiêu chuẩn trên ngữ liệu văn bản dài có cấu trúc.
              </p>
            </div>

            <div className="problem-three-cards">
              <div className="problem-feature-card">
                <div className="card-top-icon red">
                  <BookOpen size={22} />
                </div>
                <h3>1. Hiện Tượng Cắt Ngắn Token (66% Cut-off)</h3>
                <p>
                  Các mô hình Dense Embedding tiêu chuẩn (như `multilingual-e5-large` hay `bge-m3`) có giới hạn
                  cửa sổ ngữ cảnh 512 tokens. Trong khi đó, một trang tài liệu thủy lợi trung bình chứa hơn 800 - 1.200 tokens.
                  Khi đưa nguyên trang vào mô hình, <strong>66,21% nội dung ở nửa sau của trang bị cắt bỏ hoàn toàn</strong>.
                </p>
                <div className="problem-metric-tag font-mono">
                  <span>Trung bình 28 trang / văn bản · 30.382 vùng phân tích</span>
                </div>
              </div>

              <div className="problem-feature-card">
                <div className="card-top-icon amber">
                  <FileSpreadsheet size={22} />
                </div>
                <h3>2. Bảng Biểu Số Liệu & OCR Quét Scan</h3>
                <p>
                  Hơn 406 bảng biểu số liệu về dung tích hữu ích, lưu lượng xả, mực nước dâng bình thường bị định dạng
                  phẳng (flat text) khi trích xuất thông thường. Điều này làm mất hoàn toàn cấu trúc hàng - cột và
                  dẫn đến việc AI trích nhầm số liệu của hàng này sang cột của hồ khác.
                </p>
                <div className="problem-metric-tag font-mono">
                  <span>406 Bảng số liệu · Nguy cơ sai lệch đơn vị quan trắc</span>
                </div>
              </div>

              <div className="problem-feature-card">
                <div className="card-top-icon blue">
                  <Split size={22} />
                </div>
                <h3>3. Multi-Evidence & Nguy Cơ Rò Rỉ Split</h3>
                <p>
                  Một câu hỏi kỹ thuật thực tế thường đòi hỏi thu hồi đồng thời nhiều trang (ví dụ: so sánh dung tích hồ tại Trang 5
                  với phương án xả lũ tại Trang 18). Nếu không khóa phân tách theo họ văn bản (document family), dữ liệu kiểm thử
                  sẽ bị rò rỉ (leakage), tạo ra điểm đánh giá giả tạo trên benchmark.
                </p>
                <div className="problem-metric-tag font-mono">
                  <span>25 QA Multi-Evidence trên DEV · Yêu cầu thu hồi đồng thời</span>
                </div>
              </div>
            </div>

            {/* The AnyRecall Flaw Warning */}
            <div className="warning-methodology-box">
              <div className="warning-icon-side">
                <ShieldAlert size={28} />
              </div>
              <div className="warning-copy">
                <strong>LỖ HỔNG PHƯƠNG PHÁP LUẬN CỦA CHỈ SỐ ANYRECALL@K</strong>
                <p>
                  Đa số các nghiên cứu RAG phổ biến chỉ đo <code>AnyRecall@K</code> (chỉ cần tìm được 1 trong số các đoạn văn
                  là tính thành công). Trong thủy lợi, tìm thấy 1 đoạn thông báo mà thiếu bảng thông số đi kèm sẽ dẫn đến
                  tính toán sai lệch nghiêm trọng. VietIrr-RAG kiên quyết định nghĩa thành công bằng <code>AllRecall@K</code>
                  — bắt buộc phải thu hồi trọn vẹn 100% tập bằng chứng tối thiểu (Minimal Sufficient Evidence Set).
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 04: SOLUTION
            ================================================================== */}
        <section id="sec-solution" className="report-section section-solution">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 04 · NGUYÊN TẮC GIẢI PHÁP</span>
              <h2 className="section-title">Định Hướng Evidence-First & Kỷ Luật Không Ảo Giác</h2>
              <p className="section-subtitle">
                Chuyển dịch từ việc sinh câu trả lời tự do sang việc truy xuất đủ tập bằng chứng có khả năng kiểm chứng.
              </p>
            </div>

            <div className="solution-pillars-row">
              <div className="pillar-editorial-card">
                <span className="pillar-digit font-mono">01</span>
                <h3>Tính Truy Nguyên Tuyệt Đối (Provenance)</h3>
                <p>
                  Mọi kết quả trả về bắt buộc gắn liền với <strong>Mã tài liệu</strong>, <strong>Số trang chính xác</strong>,
                  <strong>Evidence ID</strong> và <strong>Mã băm SHA-256</strong> của tài liệu gốc.
                  Không một luận điểm nào được đưa ra mà không có bằng chứng đối chiếu trực tiếp trên file PDF.
                </p>
                <ul className="pillar-bullets">
                  <li><CheckCircle2 size={14} className="text-teal" /> Mở trực tiếp trang PDF ngay trong ứng dụng</li>
                  <li><CheckCircle2 size={14} className="text-teal" /> Giữ nguyên văn trích đoạn, không paraphrase làm méo mó số liệu</li>
                </ul>
              </div>

              <div className="pillar-editorial-card highlight">
                <span className="pillar-digit font-mono">02</span>
                <h3>Thu Hồi Đủ Tập Bằng Chứng (MSES)</h3>
                <p>
                  Đơn vị thành công được định nghĩa là <strong>Minimal Sufficient Evidence Set (MSES)</strong>:
                  Tập bằng chứng nhỏ nhất nhưng đủ để một kỹ sư thủy lợi đưa ra kết luận kỹ thuật mà không cần phỏng đoán.
                </p>
                <div className="math-formula-box font-mono">
                  AllRecall@K = (1/N) * ∑ 𝟙[ G_q ⊆ TopK(q) ]
                </div>
                <small className="math-caption">Trong đó G_q là tập hợp toàn bộ các bằng chứng bắt buộc của câu hỏi q.</small>
              </div>

              <div className="pillar-editorial-card">
                <span className="pillar-digit font-mono">03</span>
                <h3>Kỷ Luật Khoa Học: Không Ảo Giác</h3>
                <p>
                  Trong giai đoạn chưa hoàn thiện Human-Gold Validation, giao diện kiên quyết định vị là
                  <strong>Evidence Search</strong>, từ chối sử dụng LLM để sinh văn bản giả định nhằm bảo toàn tính trung thực của kết quả nghiên cứu.
                </p>
                <ul className="pillar-bullets">
                  <li><CheckCircle2 size={14} className="text-teal" /> Triệt tiêu 100% nguy cơ hallucination</li>
                  <li><CheckCircle2 size={14} className="text-teal" /> Đảm bảo độ tin cậy tuyệt đối trước hội đồng khoa học</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 05: SYSTEM ARCHITECTURE
            ================================================================== */}
        <section id="sec-architecture" className="report-section section-architecture">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 05 · KIẾN TRÚC HỆ THỐNG</span>
              <h2 className="section-title">Sơ Đồ Kiến Trúc Luồng Dữ Liệu Đa Tầng</h2>
              <p className="section-subtitle">
                Mô hình kỹ thuật biểu diễn luồng dữ liệu từ văn bản thô đến bằng chứng được kiểm chứng.
              </p>
            </div>

            {/* Clean 2D Vector Architectural Diagram */}
            <div className="arch-diagram-wrapper">
              <svg viewBox="0 0 1100 320" fill="none" xmlns="http://www.w3.org/2000/svg" className="arch-svg-diagram">
                {/* Node 1: Ingest */}
                <rect x="20" y="90" width="140" height="140" rx="10" fill="#FFFFFF" stroke="#D1D5DB" strokeWidth="1.5" />
                <text x="90" y="130" textAnchor="middle" fill="#1E5A65" fontSize="12" fontWeight="700" fontFamily="sans-serif">93 PDF VẬN HÀNH</text>
                <text x="90" y="155" textAnchor="middle" fill="#6B7280" fontSize="10" fontFamily="monospace">PyMuPDF Parser</text>
                <text x="90" y="175" textAnchor="middle" fill="#111827" fontSize="11" fontWeight="600" fontFamily="sans-serif">27.144 Vùng</text>
                <text x="90" y="195" textAnchor="middle" fill="#9CA3AF" fontSize="9" fontFamily="monospace">SHA-256 Hashed</text>

                {/* Connector 1 -> 2 */}
                <path d="M160 160 H210" stroke="#1E5A65" strokeWidth="2" strokeDasharray="4 4" />
                <polygon points="215,160 205,155 205,165" fill="#1E5A65" />

                {/* Node 2: Windowing */}
                <rect x="215" y="90" width="150" height="140" rx="10" fill="#FFFFFF" stroke="#1E5A65" strokeWidth="2" />
                <text x="290" y="125" textAnchor="middle" fill="#1E5A65" fontSize="11" fontWeight="800" fontFamily="sans-serif">CỬA SỔ TRƯỢT P2</text>
                <text x="290" y="150" textAnchor="middle" fill="#059669" fontSize="12" fontWeight="700" fontFamily="sans-serif">384 Tokens</text>
                <text x="290" y="170" textAnchor="middle" fill="#6B7280" fontSize="10" fontFamily="monospace">Overlap 128 tok</text>
                <text x="290" y="195" textAnchor="middle" fill="#111827" fontSize="10" fontWeight="600" fontFamily="sans-serif">0% Cut-off Token</text>

                {/* Connector 2 -> 3 */}
                <path d="M365 160 H415" stroke="#1E5A65" strokeWidth="2" />
                <polygon points="420,160 410,155 410,165" fill="#1E5A65" />

                {/* Node 3: Dual Stream */}
                <rect x="420" y="50" width="160" height="100" rx="8" fill="#FFFFFF" stroke="#D1D5DB" strokeWidth="1.5" />
                <text x="500" y="85" textAnchor="middle" fill="#111827" fontSize="11" fontWeight="700" fontFamily="sans-serif">BM25 LEXICAL</text>
                <text x="500" y="105" textAnchor="middle" fill="#6B7280" fontSize="10" fontFamily="monospace">Unicode NFC Tok</text>
                <text x="500" y="125" textAnchor="middle" fill="#1E5A65" fontSize="10" fontFamily="sans-serif">Khớp từ chuyên ngành</text>

                <rect x="420" y="170" width="160" height="100" rx="8" fill="#FFFFFF" stroke="#D1D5DB" strokeWidth="1.5" />
                <text x="500" y="205" textAnchor="middle" fill="#111827" fontSize="11" fontWeight="700" fontFamily="sans-serif">E5 DENSE EMBED</text>
                <text x="500" y="225" textAnchor="middle" fill="#6B7280" fontSize="10" fontFamily="monospace">1024-dim Vector</text>
                <text x="500" y="245" textAnchor="middle" fill="#1E5A65" fontSize="10" fontFamily="sans-serif">Ngữ nghĩa lưu vực</text>

                {/* Connector 3 -> 4 */}
                <path d="M580 100 L630 145" stroke="#1E5A65" strokeWidth="1.5" />
                <path d="M580 220 L630 175" stroke="#1E5A65" strokeWidth="1.5" />
                <polygon points="635,160 625,152 625,168" fill="#1E5A65" />

                {/* Node 4: Fusion */}
                <rect x="635" y="90" width="140" height="140" rx="10" fill="#FFFFFF" stroke="#D1D5DB" strokeWidth="1.5" />
                <text x="705" y="130" textAnchor="middle" fill="#111827" fontSize="11" fontWeight="700" fontFamily="sans-serif">RRF FUSION</text>
                <text x="705" y="155" textAnchor="middle" fill="#6B7280" fontSize="10" fontFamily="monospace">k = 60 constant</text>
                <text x="705" y="175" textAnchor="middle" fill="#1E5A65" fontSize="10" fontWeight="600" fontFamily="sans-serif">Hợp nhất hạng</text>
                <text x="705" y="195" textAnchor="middle" fill="#9CA3AF" fontSize="9" fontFamily="monospace">Tie-breaking</text>

                {/* Connector 4 -> 5 */}
                <path d="M775 160 H825" stroke="#1E5A65" strokeWidth="2" />
                <polygon points="830,160 820,155 820,165" fill="#1E5A65" />

                {/* Node 5: Page-to-Region Routing */}
                <rect x="830" y="90" width="150" height="140" rx="10" fill="#FFFFFF" stroke="#1E5A65" strokeWidth="2" />
                <text x="905" y="125" textAnchor="middle" fill="#1E5A65" fontSize="11" fontWeight="800" fontFamily="sans-serif">PAGE ROUTING P2</text>
                <text x="905" y="150" textAnchor="middle" fill="#059669" fontSize="13" fontWeight="800" fontFamily="monospace">Recall@20: 0.742</text>
                <text x="905" y="170" textAnchor="middle" fill="#6B7280" fontSize="10" fontFamily="sans-serif">Lọc Top-10 Trang</text>
                <text x="905" y="190" textAnchor="middle" fill="#111827" fontSize="10" fontWeight="600" fontFamily="sans-serif">+4.1% vs P1</text>

                {/* Connector 5 -> 6 */}
                <path d="M980 160 H1010" stroke="#1E5A65" strokeWidth="2" />
                <polygon points="1015,160 1005,155 1005,165" fill="#1E5A65" />

                {/* Node 6: In-App PDF Output */}
                <rect x="1015" y="90" width="75" height="140" rx="8" fill="#EDF6F7" stroke="#1E5A65" strokeWidth="1.5" />
                <text x="1052" y="140" textAnchor="middle" fill="#1E5A65" fontSize="10" fontWeight="700" fontFamily="sans-serif">IN-APP</text>
                <text x="1052" y="160" textAnchor="middle" fill="#1E5A65" fontSize="10" fontWeight="700" fontFamily="sans-serif">PDF</text>
                <text x="1052" y="180" textAnchor="middle" fill="#1E5A65" fontSize="9" fontFamily="sans-serif">VIEWER</text>
              </svg>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 06: DEEP DIVE INTO PIPELINE (SCROLLYTELLING)
            ================================================================== */}
        <section id="sec-pipeline" className="report-section section-pipeline-scrolly">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 06 · GIẢI PHẪU CHI TIẾT PIPELINE</span>
              <h2 className="section-title">Hành Trình Dữ Liệu Từng Bước (Interactive Scrollytelling)</h2>
              <p className="section-subtitle">
                Theo dõi chuyển động dữ liệu qua 6 chặng kỹ thuật được kiểm chứng. Nhấn vào từng chặng hoặc cuộn để khám phá.
              </p>
            </div>

            <div className="scrolly-layout-grid">
              {/* Left Column: Interactive Explanation Steps */}
              <div className="scrolly-steps-column">
                {PIPELINE_STEPS.map((step) => {
                  const isActive = activeStepId === step.id
                  return (
                    <article
                      key={step.id}
                      className={`scrolly-step-card ${isActive ? 'is-focused' : ''}`}
                      onClick={() => setActiveStepId(step.id)}
                    >
                      <div className="step-card-meta">
                        <span className="step-badge font-mono">BƯỚC {step.num}</span>
                        <span className="step-tech-badge font-mono">{step.tech}</span>
                      </div>
                      <h3 className="step-heading">{step.title}</h3>
                      <p className="step-summary-text">{step.summary}</p>
                      <ul className="step-specs-list">
                        {step.specs.map((spec, i) => (
                          <li key={i}>
                            <span className="spec-dot" />
                            <span>{spec}</span>
                          </li>
                        ))}
                      </ul>
                    </article>
                  )
                })}
              </div>

              {/* Right Column: Sticky Visual Inspector */}
              <div className="scrolly-sticky-visual-column">
                <div className="sticky-visual-card">
                  <div className="sticky-head">
                    <span className="sticky-tag font-mono">DYNAMIC PIPELINE INSPECTOR</span>
                    <span className="sticky-status-dot" />
                  </div>

                  {(() => {
                    const activeStep = PIPELINE_STEPS.find((s) => s.id === activeStepId) || PIPELINE_STEPS[0]
                    return (
                      <div className="sticky-content-body">
                        <div className="sticky-step-num font-mono">GIAI ĐOẠN {activeStep.num}</div>
                        <h4 className="sticky-title">{activeStep.title}</h4>
                        <div className="sticky-tech font-mono">{activeStep.tech}</div>

                        <div className="sticky-abstract">
                          {activeStep.summary}
                        </div>

                        <div className="sticky-verification-box">
                          <span className="v-label font-mono">THÔNG SỐ TRIỂN KHAI THỰC TẾ:</span>
                          <div className="v-items">
                            {activeStep.specs.map((spec, idx) => (
                              <div key={idx} className="v-item font-mono">
                                <Check size={12} className="text-emerald" />
                                <span>{spec}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="sticky-step-stepper">
                          {PIPELINE_STEPS.map((s) => (
                            <button
                              key={s.id}
                              type="button"
                              className={`mini-step-btn ${s.id === activeStepId ? 'active' : ''}`}
                              onClick={() => setActiveStepId(s.id)}
                            >
                              {s.num}
                            </button>
                          ))}
                        </div>
                      </div>
                    )
                  })()}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 07: PRODUCT DEMONSTRATION
            ================================================================== */}
        <section id="sec-demo" className="report-section section-demo">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 07 · TRÌNH DIỄN HỆ THỐNG</span>
              <h2 className="section-title">Kiểm Chứng Trực Tiếp Trên Bộ Bằng Chứng Thật</h2>
              <p className="section-subtitle">
                Trải nghiệm tra cứu có gắn In-App PDF Viewer được vận hành trực tiếp trên dữ liệu thủy lợi.
              </p>
            </div>

            <div className="demo-showcase-card">
              <div className="demo-card-left">
                <span className="demo-badge font-mono">TRƯỜNG HỢP KIỂM CHỨNG: DEV QA #V3_CORE_00351</span>
                <h3 className="demo-query-title">
                  "Theo dự báo nguồn nước phục vụ sản xuất nông nghiệp thuộc tỉnh Ninh Bình năm 2019, dung tích bình quân của các hồ chứa tính đến tháng 5 đạt bao nhiêu %?"
                </h3>
                <p className="demo-result-quote">
                  Bằng chứng trích xuất từ <strong>Bản tin dự báo nguồn nước Lưu vực thượng nguồn sông Đà</strong> (Cục Thủy lợi):<br />
                  <em>« Nguồn nước trữ của các hồ chứa hiện tại đều ở mức trung bình (trung bình 38%). Tính đến tháng 5/2019, dung tích bình quân đạt 68,4% so với thiết kế (Wtk = 124,5 tr.m3) »</em>
                </p>

                <div className="demo-provenance-meta font-mono">
                  <span>Mã tài liệu: <strong>IRR_CTL_2019_d9169102</strong></span>
                  <span>Vị trí: <strong>Trang 4</strong></span>
                  <span>Mã băm SHA-256: <strong>Khớp 100%</strong></span>
                </div>

                <div className="demo-actions-row">
                  <button
                    type="button"
                    className="btn-demo-primary"
                    onClick={() => handleLaunchWorkspace('Theo dự báo nguồn nước phục vụ sản xuất nông nghiệp thuộc tỉnh Ninh Bình năm 2019, dung tích bình quân của các hồ chứa tính đến tháng 5 đạt bao nhiêu %?')}
                  >
                    <span>Mở Bàn Làm Việc RAG & PDF Viewer</span>
                    <ArrowRight size={15} />
                  </button>
                  <Link to="/app" className="btn-demo-secondary">
                    <span>Xem toàn bộ 93 tài liệu</span>
                    <ArrowUpRight size={14} />
                  </Link>
                </div>
              </div>

              <div className="demo-card-right">
                <div className="viewer-preview-graphic">
                  <div className="preview-top-bar font-mono">
                    <BookOpen size={13} className="text-teal" />
                    <span>IN-APP PDF VIEWER · TRANG 4</span>
                  </div>
                  <div className="preview-body">
                    <div className="preview-canvas-placeholder">
                      <div className="doc-paper-rep">
                        <div className="paper-line header" />
                        <div className="paper-line" />
                        <div className="paper-line highlight" />
                        <div className="paper-line" />
                        <div className="paper-line short" />
                        <div className="paper-table-rep">
                          <div className="t-row h" />
                          <div className="t-row" />
                          <div className="t-row active" />
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="preview-footer-note font-mono">
                    <ShieldCheck size={12} className="text-emerald" />
                    <span>Mở tự động đúng trang 4 · Không tải file về máy</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 08: EXPERIMENTAL METHODOLOGY
            ================================================================== */}
        <section id="sec-methodology" className="report-section section-methodology">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 08 · DỮ LIỆU & PHƯƠNG PHÁP THỰC NGHIỆM</span>
              <h2 className="section-title">Ngữ Liệu Thủy Lợi Chuẩn Hóa & Giao Thức Đánh Giá Độc Lập</h2>
              <p className="section-subtitle">
                Đặc tả kỹ thuật của kho ngữ liệu V4 vận hành hiện hành, baseline đối chứng V3.2 và quy chuẩn kiểm soát không rò rỉ.
              </p>
            </div>

            <div className="methodology-grid">
              <div className="method-spec-card">
                <h3 className="spec-heading">1. Ngữ Liệu Vận Hành Hiện Hành (V4_R6_FROZEN)</h3>
                <p>
                  Toàn bộ tài liệu pháp quy và báo cáo kỹ thuật đang phục vụ tra cứu thực tế trên hệ thống:
                </p>
                <div className="spec-table-list font-mono">
                  <div className="spec-row">
                    <span>Số lượng PDF chính thống:</span>
                    <strong>{OPERATIONAL_CORPUS_V4.documentCount} tài liệu</strong>
                  </div>
                  <div className="spec-row">
                    <span>Tổng số trang PDF:</span>
                    <strong>{OPERATIONAL_CORPUS_V4.pageCount.toLocaleString('vi-VN')} trang</strong>
                  </div>
                  <div className="spec-row">
                    <span>Đơn vị bằng chứng (Evidence Units):</span>
                    <strong>{OPERATIONAL_CORPUS_V4.evidenceUnitCount.toLocaleString('vi-VN')} đơn vị</strong>
                  </div>
                  <div className="spec-row">
                    <span>Phân đoạn văn bản / Bảng biểu:</span>
                    <strong>27.053 text / 91 table</strong>
                  </div>
                </div>
              </div>

              <div className="method-spec-card">
                <h3 className="spec-heading">2. Bộ Ngữ Liệu Đối Chứng & DEV Set (n=93)</h3>
                <p>
                  Tập baseline V3.2 và bộ câu hỏi đánh giá độc lập DEV-93 với giao thức kiểm soát rò rỉ nghiêm ngặt:
                </p>
                <div className="spec-table-list font-mono">
                  <div className="spec-row">
                    <span>Baseline đối chứng V3.2:</span>
                    <strong>89 PDF / 2.479 trang / 27.045 units</strong>
                  </div>
                  <div className="spec-row">
                    <span>Tập câu hỏi kiểm nghiệm độc lập:</span>
                    <strong>93 câu hỏi (DEV-93)</strong>
                  </div>
                  <div className="spec-row">
                    <span>Rò rỉ phân tách Train/Dev:</span>
                    <strong className="text-emerald">0.00% (Theo họ văn bản)</strong>
                  </div>
                  <div className="spec-row">
                    <span>Kiểm soát rò rỉ đáp án (Oracle):</span>
                    <strong className="text-emerald">0.00% (Strict Blind Prompting)</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ==================================================================
            SECTION 09: EVALUATION & RESULTS
            ================================================================== */}
        <section id="sec-evaluation" className="report-section section-evaluation">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 09 · KẾT QUẢ THỰC NGHIỆM</span>
              <h2 className="section-title">Báo Cáo Số Liệu & Phát Hiện Khoa Học</h2>
              <p className="section-subtitle">
                Đánh giá định lượng trên DEV Set (n=93) và bài học thực chứng từ các kết quả âm tính.
              </p>
            </div>

            {/* Scientific Tabs */}
            <div className="eval-tabs-bar">
              <button
                type="button"
                className={`eval-tab-btn ${activeEvalTab === 'r6' ? 'is-active' : ''}`}
                onClick={() => setActiveEvalTab('r6')}
              >
                <Trophy size={14} />
                <span>R6 Frozen Pipeline (Vận Hành Hiện Hành)</span>
              </button>
              <button
                type="button"
                className={`eval-tab-btn ${activeEvalTab === 'p2' ? 'is-active' : ''}`}
                onClick={() => setActiveEvalTab('p2')}
              >
                <BarChart3 size={14} />
                <span>Nghiên Cứu Stage P2: Windowed Routing</span>
              </button>
              <button
                type="button"
                className={`eval-tab-btn ${activeEvalTab === 'b2' ? 'is-active' : ''}`}
                onClick={() => setActiveEvalTab('b2')}
              >
                <Layers size={14} />
                <span>Baseline B2 (So Sánh Mô Hình)</span>
              </button>
              <button
                type="button"
                className={`eval-tab-btn ${activeEvalTab === 'negative' ? 'is-active' : ''}`}
                onClick={() => setActiveEvalTab('negative')}
              >
                <AlertTriangle size={14} />
                <span>Bài Học Thực Chứng & Fail-Closed Safety</span>
              </button>
            </div>

            {/* TAB CONTENT 0: R6 Frozen Baseline */}
            {activeEvalTab === 'r6' && (
              <div className="eval-pane-wrap">
                <div className="eval-metrics-hero-grid">
                  <div className="eval-metric-box hero-accent">
                    <span className="m-label font-mono">Candidate Hit@100 (R6)</span>
                    <strong className="m-val font-mono">91,40%</strong>
                    <span className="m-gain font-mono">85 / 93 câu hỏi DEV có gold trong Top 100</span>
                    <small>BM25 + Dense BGE-M3 + Reranker BGE-v2-m3</small>
                  </div>

                  <div className="eval-metric-box">
                    <span className="m-label font-mono">Page Hit@5 (Budget B)</span>
                    <strong className="m-val font-mono text-emerald">67,74%</strong>
                    <span className="m-sub">63 / 93 câu hỏi giữ gold trong Top 5 trang</span>
                    <small>Ngân sách 5 trang duy nhất phục vụ Context</small>
                  </div>

                  <div className="eval-metric-box">
                    <span className="m-label font-mono">Evidence Page Hit@5</span>
                    <strong className="m-val font-mono text-amber">61,29%</strong>
                    <span className="m-sub">57 / 93 câu hỏi trúng vùng bằng chứng chính xác</span>
                    <small>Cung cấp bằng chứng bảng và text cho Qwen</small>
                  </div>
                </div>

                <div className="table-card-container">
                  <table className="clean-scientific-table">
                    <thead>
                      <tr>
                        <th>Chỉ số Retrieval (R6)</th>
                        <th>Tỷ lệ / Giá trị</th>
                        <th>Mẫu thực nghiệm</th>
                        <th>Phân loại & Định nghĩa</th>
                        <th>Nguồn đối chiếu Artifact</th>
                      </tr>
                    </thead>
                    <tbody>
                      {VERIFIED_R6_METRICS.map((m) => (
                        <tr key={m.metricKey}>
                          <td><strong>{m.name}</strong></td>
                          <td><span className="font-mono text-emerald" style={{ fontWeight: 700 }}>{m.value}</span></td>
                          <td><code>{m.fraction}</code></td>
                          <td>{m.description}</td>
                          <td><code className="text-muted" style={{ fontSize: '0.65rem' }}>{m.artifactSource}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB CONTENT 1: P2 Breakthrough */}
            {activeEvalTab === 'p2' && (
              <div className="eval-pane-wrap">
                <div className="eval-metrics-hero-grid">
                  <div className="eval-metric-box hero-accent">
                    <span className="m-label font-mono">Complete-Page Recall@20</span>
                    <strong className="m-val font-mono">0.742</strong>
                    <span className="m-gain font-mono">+4,1% so với P1 Single-Page (0.701)</span>
                    <small>Cấu hình đề xuất B3_WINDOW_TOP10 (384 tokens / overlap 128)</small>
                  </div>

                  <div className="eval-metric-box">
                    <span className="m-label font-mono">Tỷ lệ Cắt Ngắn Token</span>
                    <strong className="m-val font-mono text-emerald">0.00%</strong>
                    <span className="m-sub">Trước phân đoạn: 66,21% trang bị cắt ngắn</span>
                    <small>6.134 cửa sổ trượt, không cửa sổ nào vượt 512 tokens</small>
                  </div>

                  <div className="eval-metric-box">
                    <span className="m-label font-mono">Số Ca Lỗi Được Phục Hồi</span>
                    <strong className="m-val font-mono text-amber">+6 QA</strong>
                    <span className="m-sub">Thu hồi thành công các bảng biểu dài ở đuôi trang</span>
                    <small>Khắc phục hoàn toàn điểm yếu cắt ngắn của Transformer</small>
                  </div>
                </div>

                <div className="table-card-container">
                  <table className="clean-scientific-table">
                    <thead>
                      <tr>
                        <th>Cấu hình Thí nghiệm</th>
                        <th>Biểu diễn Trang</th>
                        <th>Ngân sách Trang</th>
                        <th>All Recall@10</th>
                        <th>All Recall@20</th>
                        <th>MRR</th>
                        <th>nDCG@10</th>
                        <th>Độ trễ TB</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td><code>B1_SINGLE_TOP10</code> (Baseline P1)</td>
                        <td>Single Full Page</td>
                        <td>Top 10</td>
                        <td>0.6495</td>
                        <td>0.7010</td>
                        <td>0.4296</td>
                        <td>0.4810</td>
                        <td>35,6 ms</td>
                      </tr>
                      <tr className="highlight-table-row">
                        <td><strong><code>B3_WINDOW_TOP10</code> (Đề xuất P2)</strong></td>
                        <td><strong>Window Max-Pool</strong></td>
                        <td><strong>Top 10</strong></td>
                        <td><strong>0.6701</strong></td>
                        <td><strong>0.7423</strong></td>
                        <td><strong>0.4306</strong></td>
                        <td><strong>0.4860</strong></td>
                        <td>56,3 ms</td>
                      </tr>
                      <tr>
                        <td><code>B4_WINDOW_TOP20</code></td>
                        <td>Window Max-Pool</td>
                        <td>Top 20</td>
                        <td>0.6598</td>
                        <td>0.7113</td>
                        <td>0.4147</td>
                        <td>0.4662</td>
                        <td>56,6 ms</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB CONTENT 2: B2 Baseline Comparison */}
            {activeEvalTab === 'b2' && (
              <div className="eval-pane-wrap">
                <div className="table-card-container">
                  <table className="clean-scientific-table">
                    <thead>
                      <tr>
                        <th>Phương pháp</th>
                        <th>Any Recall@10</th>
                        <th>All Recall@20 (MSES)</th>
                        <th>MRR</th>
                        <th>nDCG@10</th>
                        <th>Nhận xét kỹ thuật</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>BM25 (Từ khóa tiếng Việt)</td>
                        <td>0.2688</td>
                        <td>0.2796</td>
                        <td>0.0950</td>
                        <td>0.1128</td>
                        <td>Từ khóa bị phân tán khi câu hỏi dùng từ đồng nghĩa chuyên ngành</td>
                      </tr>
                      <tr>
                        <td>multilingual-e5-large (Dense)</td>
                        <td>0.5161</td>
                        <td>0.5484</td>
                        <td>0.2736</td>
                        <td>0.2937</td>
                        <td>Nắm bắt tốt ngữ nghĩa nhưng bị cắt ngắn ở các trang dài vượt 512 tokens</td>
                      </tr>
                      <tr>
                        <td>Hybrid RRF (BM25 + E5)</td>
                        <td>0.4839</td>
                        <td>0.4946</td>
                        <td>0.2627</td>
                        <td>0.2767</td>
                        <td>Hợp nhất trực tiếp trên không gian vùng bị loãng điểm số</td>
                      </tr>
                      <tr className="highlight-table-row">
                        <td><strong>Page→Region (Phân tầng)</strong></td>
                        <td><strong>0.6452</strong></td>
                        <td><strong>0.5914</strong></td>
                        <td><strong>0.2997</strong></td>
                        <td><strong>0.3412</strong></td>
                        <td><strong>Vượt trội: Lọc trang trước giúp giảm 98% không gian tìm kiếm</strong></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* TAB CONTENT 3: Negative Results & Integrity */}
            {activeEvalTab === 'negative' && (
              <div className="eval-pane-wrap">
                <div className="negative-results-editorial">
                  <h3>Kỷ Luật Khoa Học: Bài Học Từ Thí Nghiệm MASH-ER và MAR-ER</h3>
                  <p>
                    Trong quá trình nghiên cứu, nhóm đã thử nghiệm hai hướng tiếp cận phức tạp: Multi-view Representation (MASH-ER)
                    và Adaptive Relevance Recovery (MAR-ER). Kết quả đem lại một phát hiện khoa học mang tính bản lề:
                  </p>
                  <div className="negative-discovery-banner">
                    <strong>PHÁT HIỆN KHOA HỌC: ĐÁNH ĐỔI COVERAGE VÀ RANK DISPLACEMENT</strong>
                    <p>
                      Mở rộng số lượng ứng viên (Coverage@100 tăng vọt từ 0.77 lên <strong>0.86</strong>) không hề giúp tăng All Recall@20,
                      ngược lại làm giảm All Recall@20 từ <strong>0.59 xuống 0.47</strong>! Nguyên nhân: Các ứng viên mới được kéo vào đã
                      chiếm chỗ và đẩy các bằng chứng vàng (gold evidence) ra ngoài ngưỡng Top-20.
                    </p>
                  </div>
                  <p className="negative-conclusion-note">
                    Nhóm bảo lưu toàn bộ các kết quả âm tính trong báo cáo để chứng minh tính trung thực khoa học,
                    tuyệt đối không "cherry-pick" số liệu để tạo cảm giác hệ thống luôn tăng trưởng.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ==================================================================
            SECTION 10: CONCLUSION & FUTURE WORK
            ================================================================== */}
        <section id="sec-conclusion" className="report-section section-conclusion">
          <div className="section-container">
            <div className="section-header-block">
              <span className="chapter-indicator font-mono">CHƯƠNG 10 · TỔNG KẾT & LỘ TRÌNH</span>
              <h2 className="section-title">Đóng Góp Cốt Lõi & Hướng Phát Triển Tiếp Theo</h2>
              <p className="section-subtitle">
                Những kết quả đã được nghiệm thu và các bước đi trong giai đoạn tiếp theo của đề tài.
              </p>
            </div>

            <div className="conclusion-two-columns">
              <div className="conclusion-card">
                <div className="c-head">
                  <Trophy size={18} className="text-teal" />
                  <h3>4 Đóng Góp Cốt Lõi Đã Hoàn Thành</h3>
                </div>
                <div className="c-items">
                  <div className="c-item">
                    <CheckCircle2 size={16} className="text-emerald" />
                    <div>
                      <strong>1. Bộ Ngữ Liệu Thủy Lợi V4 Chuẩn Hóa</strong>
                      <p>93 tài liệu chính thống, 2.578 trang, 27.144 đơn vị bằng chứng, 0.00% leakage phân tách họ tài liệu.</p>
                    </div>
                  </div>
                  <div className="c-item">
                    <CheckCircle2 size={16} className="text-emerald" />
                    <div>
                      <strong>2. Pipeline R6 Hybrid Retrieval Đông Băng</strong>
                      <p>BM25 + Dense BGE-M3 + Reranker BGE-v2-m3 đạt 91,40% Candidate Hit@100 và 67,74% Page Hit@5 trên DEV-93.</p>
                    </div>
                  </div>
                  <div className="c-item">
                    <CheckCircle2 size={16} className="text-emerald" />
                    <div>
                      <strong>3. Qwen2.5:7B Local & Citation Guard</strong>
                      <p>Sinh câu trả lời tiếng Việt tự nhiên kèm trích dẫn số trang chính xác; chặn 100% citation giả mạo theo cơ chế fail-closed.</p>
                    </div>
                  </div>
                  <div className="c-item">
                    <CheckCircle2 size={16} className="text-emerald" />
                    <div>
                      <strong>4. Nền Tảng In-App PDF Evidence Search</strong>
                      <p>Tra cứu có đối chiếu nguồn gốc, xem trực tiếp PDF ngay trên web tại đúng trang nguồn, kiểm chứng mã SHA-256.</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="conclusion-card">
                <div className="c-head">
                  <Flag size={18} className="text-teal" />
                  <h3>Hạn Chế Thực Chứng & Lộ Trình Phát Triển</h3>
                </div>
                <div className="c-items">
                  <div className="c-item">
                    <span className="step-index font-mono">01</span>
                    <div>
                      <strong>Nguyên Tắc Fail-Closed Khi Thiếu Bằng Chứng</strong>
                      <p>Khi câu hỏi mơ hồ hoặc tài liệu thiếu dữ kiện, hệ thống từ chối an toàn thay vì bịa đặt số liệu (hallucination).</p>
                    </div>
                  </div>
                  <div className="c-item">
                    <span className="step-index font-mono">02</span>
                    <div>
                      <strong>Thách Thức Chất Lượng Quét Bảng OCR Cũ</strong>
                      <p>Các tài liệu lưu trữ cũ có bảng biểu scan mờ có thể làm gián đoạn việc liên kết hàng cột; cần tiếp tục phát triển parser chuyên dụng.</p>
                    </div>
                  </div>
                  <div className="c-item">
                    <span className="step-index font-mono">03</span>
                    <div>
                      <strong>Ontology Verifier Vận Hành Ở Shadow Mode</strong>
                      <p>Hệ thống tích hợp thẩm định quan hệ 5 chiều ở chế độ quan trắc telemetry, bảo đảm câu trả lời mặc định không bị can thiệp sai lệch.</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Final Q&A & Action Callout */}
            <div className="final-qa-callout">
              <div className="qa-left">
                <h3>CẢM ƠN QUÝ THẦY CÔ VÀ HỘI ĐỒNG ĐÃ THEO DÕI!</h3>
                <p>Nhóm nghiên cứu sẵn sàng bước vào phiên Hỏi & Đáp (Q&A) và Trình diễn trực tiếp hệ thống.</p>
              </div>
              <div className="qa-right">
                <button
                  type="button"
                  className="btn-final-launch"
                  onClick={() => handleLaunchWorkspace()}
                >
                  <Play size={16} />
                  <span>Trải Nghiệm RAG Workspace Ngay</span>
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* ─── Minimalist Footer ─── */}
      <footer className="report-footer">
        <div className="footer-container">
          <div className="footer-left">
            <strong>VietIrr-RAG · Hydraulic Intelligence Research Group</strong>
            <p>Trường Đại học Thủy Lợi (TLU) · Khoa Công Nghệ Thông Tin · 2026</p>
          </div>
          <div className="footer-right font-mono">
            <span>Corpus V4_R6_FROZEN · Phân tách Họ Văn bản (Zero Leakage)</span>
            <span>FastAPI Backend · React 19 Client · PDF.js In-App Engine</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
