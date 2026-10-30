import { Award, Compass, Droplets, GraduationCap, Sparkles, User, Users } from 'lucide-react'

export function Scene01Opening() {
  return (
    <div className="scene-slide scene-opening">
      <div className="opening-badge-row">
        <span className="inst-badge">
          <GraduationCap size={15} />
          <span>TRƯỜNG ĐẠI HỌC THỦY LỢI (TLU) · KHOA CÔNG NGHỆ THÔNG TIN</span>
        </span>
        <span className="sub-badge">ĐỒ ÁN NGHIÊN CỨU & ỨNG DỤNG HỌC SÂU (2026)</span>
      </div>

      <div className="opening-hero-content">
        <p className="project-code font-mono">VIETIRR-RAG · R6 FROZEN PIPELINE · V4 OPERATIONAL CORPUS</p>
        <h1 className="opening-title">
          Truy Xuất Bằng Chứng Từ Tài Liệu Thủy Lợi Tiếng Việt Dài
        </h1>
        <p className="opening-lead">
          Hệ thống Evidence-first Retrieval có kiểm chứng (Provenance-centric) cho văn bản pháp lý,
          báo cáo quy hoạch lưu vực và số liệu quan trắc hồ chứa - đập dâng.
        </p>
      </div>

      <div className="opening-meta-grid">
        <div className="meta-card">
          <div className="meta-card-header">
            <Users size={16} />
            <span>Sinh viên thực hiện</span>
          </div>
          <p className="meta-highlight">Nhóm Nghiên cứu VietIrr-RAG</p>
          <small className="meta-sub">Chuyên ngành Khoa học Dữ liệu & Trí tuệ Nhân tạo</small>
        </div>

        <div className="meta-card">
          <div className="meta-card-header">
            <User size={16} />
            <span>Giảng viên hướng dẫn</span>
          </div>
          <p className="meta-highlight">Bộ môn Học sâu & Xử lý Ngôn ngữ Tự nhiên</p>
          <small className="meta-sub">Khoa CNTT — Đại học Thủy Lợi</small>
        </div>

        <div className="meta-card">
          <div className="meta-card-header">
            <Award size={16} />
            <span>Trọng tâm học thuật</span>
          </div>
          <p className="meta-highlight">Evidence-First vs Hallucination</p>
          <small className="meta-sub">Đo lường Complete-Evidence Recall (AllRecall@K)</small>
        </div>
      </div>

      <div className="opening-footer-hint">
        <Sparkles size={14} />
        <span>Sử dụng phím <strong>Mũi tên phải (→)</strong> hoặc <strong>Phím cách (Space)</strong> để chuyển tiếp slide</span>
      </div>
    </div>
  )
}
