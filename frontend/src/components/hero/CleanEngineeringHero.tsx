import { ArrowRight, BookOpen, CheckCircle2, ChevronDown, Database, Droplets, Layers, ShieldCheck, Tv } from 'lucide-react'
import { Link } from 'react-router-dom'
import { OPERATIONAL_CORPUS_V4 } from '../../config/systemMetrics'

interface CleanEngineeringHeroProps {
  onScrollToWorkspace: () => void
}

export function CleanEngineeringHero({ onScrollToWorkspace }: CleanEngineeringHeroProps) {
  return (
    <section className="clean-hero-section">
      {/* Background Subtle Contour Grid */}
      <div className="hero-contour-bg" aria-hidden="true">
        <svg viewBox="0 0 1440 480" fill="none" xmlns="http://www.w3.org/2000/svg" className="contour-svg">
          <path d="M-100 240C200 160 500 320 800 220C1100 120 1300 260 1600 200" stroke="rgba(30, 90, 101, 0.09)" strokeWidth="1.5" />
          <path d="M-100 280C220 200 480 360 820 260C1120 160 1320 300 1600 240" stroke="rgba(30, 90, 101, 0.07)" strokeWidth="1.2" />
          <path d="M-100 320C240 240 460 400 840 300C1140 200 1340 340 1600 280" stroke="rgba(30, 90, 101, 0.05)" strokeWidth="1" />
          <path d="M-100 360C260 280 440 440 860 340C1160 240 1360 380 1600 320" stroke="rgba(30, 90, 101, 0.04)" strokeWidth="0.8" />
        </svg>
      </div>

      <div className="clean-hero-container">
        {/* Top Product Badge */}
        <div className="hero-product-pill">
          <span className="pill-dot" />
          <span className="pill-text font-mono">VIETIRR-RAG · R6 FROZEN PIPELINE · V4 OPERATIONAL CORPUS</span>
        </div>

        {/* Confident Headline */}
        <h1 className="hero-headline">
          Truy xuất bằng chứng kỹ thuật<br />
          <span className="text-accent">từ tài liệu thủy lợi Việt Nam.</span>
        </h1>

        {/* Clear, Restrained Subtitle */}
        <p className="hero-description">
          Hệ thống tra cứu có đối chiếu nguồn gốc dành cho văn bản pháp lý, báo cáo quy hoạch lưu vực
          và số liệu hồ chứa — đảm bảo mỗi kết quả đều đi kèm số trang và file PDF gốc.
        </p>

        {/* Action Buttons */}
        <div className="hero-cta-group">
          <button
            type="button"
            className="btn-primary-action"
            onClick={onScrollToWorkspace}
          >
            <span>Mở Bàn làm việc RAG</span>
            <ArrowRight size={15} />
          </button>

          <Link to="/presentation" className="btn-secondary-action">
            <Tv size={15} />
            <span>Chế độ Báo cáo Hội đồng (16:9)</span>
          </Link>
        </div>

        {/* 4 Trust & Integrity Metric Cards — Synchronized with V4_R6_FROZEN */}
        <div className="hero-trust-grid">
          <div className="trust-item">
            <div className="trust-number font-mono">{OPERATIONAL_CORPUS_V4.documentCount}</div>
            <div className="trust-label">Tài liệu PDF chính thống (V4)</div>
            <div className="trust-sub">2.578 trang · Cục Thủy lợi & SIWRP</div>
          </div>

          <div className="trust-item">
            <div className="trust-number font-mono">{OPERATIONAL_CORPUS_V4.evidenceUnitCount.toLocaleString('vi-VN')}</div>
            <div className="trust-label">Đơn vị bằng chứng</div>
            <div className="trust-sub">27.053 đoạn văn + 91 bảng biểu</div>
          </div>

          <div className="trust-item">
            <div className="trust-number font-mono highlight">91.40%</div>
            <div className="trust-label">Candidate Hit@100 (R6)</div>
            <div className="trust-sub">Page Hit@5: 67.74% trên DEV-93</div>
          </div>

          <div className="trust-item">
            <div className="trust-number font-mono good">0.00%</div>
            <div className="trust-label">Rò rỉ phân tách (Leakage)</div>
            <div className="trust-sub">Phân tách Train/Dev theo họ văn bản</div>
          </div>
        </div>
      </div>
    </section>
  )
}
