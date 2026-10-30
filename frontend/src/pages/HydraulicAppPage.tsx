import { ArrowRight, BookOpen, Droplets, ExternalLink, Layers, Search, ShieldCheck, Tv } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { CleanEngineeringHero } from '../components/hero/CleanEngineeringHero'
import { RagWorkspace } from '../components/rag/RagWorkspace'

export function HydraulicAppPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const currentQuery = searchParams.get('q') || ''
  const fromPresentation = searchParams.get('from') === 'presentation'
  const returnSlide = searchParams.get('slide') || '4' // Slide 05 is index 4

  const handleReturnToPresentation = () => {
    navigate(`/presentation?slide=${returnSlide}`)
  }

  const handleScrollToWorkspace = () => {
    const el = document.getElementById('workspace-anchor')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="clean-app-root">
      {/* ─── Presentation Return Banner (If coming from Live Demo Bridge) ─── */}
      {fromPresentation && (
        <div className="clean-presentation-banner">
          <div className="banner-left-info">
            <span className="live-demo-tag font-mono">LIVE DEMO CHẾ ĐỘ THUYẾT TRÌNH</span>
            <span className="banner-slide-notice">Đang mở RAG Workspace · Vị trí bài báo cáo: Slide {Number(returnSlide) + 1}</span>
          </div>
          <button
            type="button"
            className="btn-return-slide"
            onClick={handleReturnToPresentation}
          >
            <span>Quay lại Bài Thuyết Trình</span>
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* ─── Clean Commercial Header / Nav Bar (Linear / Vercel style) ─── */}
      <header className="clean-top-header">
        <div className="header-inner">
          <div className="header-brand">
            <Droplets size={18} className="brand-icon text-teal" />
            <span className="brand-title">VietIrr-RAG</span>
            <span className="brand-badge font-mono">HYDRAULIC INTELLIGENCE</span>
          </div>

          <nav className="header-nav-links">
            <button
              type="button"
              className="nav-link-btn"
              onClick={handleScrollToWorkspace}
            >
              <span>Không gian Tra cứu</span>
            </button>

            <Link to="/presentation" className="btn-nav-presentation">
              <Tv size={14} />
              <span>Báo cáo Khoa học</span>
            </Link>
          </nav>
        </div>
      </header>

      {/* ─── Clean Commercial Architectural Hero ─── */}
      <CleanEngineeringHero onScrollToWorkspace={handleScrollToWorkspace} />

      {/* ─── Functional RAG Workspace ─── */}
      <section className="workspace-main-wrapper">
        <RagWorkspace initialQuery={currentQuery} />
      </section>

      {/* ─── Minimalist Footer ─── */}
      <footer className="clean-footer">
        <div className="footer-inner">
          <div className="footer-col-brand">
            <strong>VietIrr-RAG</strong>
            <p>Hệ thống truy xuất bằng chứng chuyên sâu cho tài liệu thủy lợi Việt Nam.</p>
          </div>
          <div className="footer-col-meta font-mono">
            <span>Trường Đại học Thủy Lợi (TLU) · Khoa CNTT</span>
            <span>Corpus V4_R6_FROZEN · Phân tách Họ Văn bản (Zero Leakage)</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
