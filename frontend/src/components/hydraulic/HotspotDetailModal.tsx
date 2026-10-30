import { ArrowRight, Compass, Database, Droplets, Info, Search, ShieldCheck, X } from 'lucide-react'
import type { HotspotInfo } from './HydraulicHotspots'

interface HotspotDetailModalProps {
  hotspot: HotspotInfo
  onClose: () => void
  onRunRagQuery: (query: string) => void
  onOpenWorkspace: () => void
}

export function HotspotDetailModal({
  hotspot,
  onClose,
  onRunRagQuery,
  onOpenWorkspace,
}: HotspotDetailModalProps) {
  return (
    <div className="hotspot-detail-panel" role="dialog" aria-labelledby="hotspot-title">
      <div className="hotspot-panel-header">
        <div className="hotspot-badge">
          <Droplets size={14} />
          <span>Thông số công trình minh họa</span>
        </div>
        <button
          type="button"
          className="hotspot-close-btn"
          onClick={onClose}
          aria-label="Đóng bảng thông số"
        >
          <X size={16} />
        </button>
      </div>

      <div className="hotspot-panel-body">
        <div className="hotspot-heading-block">
          <h2 id="hotspot-title">{hotspot.title}</h2>
          <p className="hotspot-subtitle">{hotspot.subtitle}</p>
        </div>

        <p className="hotspot-description">{hotspot.description}</p>

        {/* Engineering Specs Grid */}
        <div className="hotspot-specs-grid">
          <div className="spec-card">
            <span className="spec-label">
              <Compass size={12} /> Cao trình
            </span>
            <strong className="spec-value">{hotspot.elevation}</strong>
          </div>
          <div className="spec-card">
            <span className="spec-label">
              <Database size={12} /> Trữ lượng / Khả năng
            </span>
            <strong className="spec-value">{hotspot.capacity}</strong>
          </div>
          <div className="spec-card">
            <span className="spec-label">
              <Droplets size={12} /> Lưu lượng thiết kế
            </span>
            <strong className="spec-value">{hotspot.flowRate}</strong>
          </div>
          <div className="spec-card">
            <span className="spec-label">
              <ShieldCheck size={12} /> Quy chuẩn kết cấu
            </span>
            <strong className="spec-value">{hotspot.structureType}</strong>
          </div>
        </div>

        {/* Sample RAG Queries */}
        <div className="hotspot-queries-section">
          <h3>
            <Search size={14} /> Câu hỏi tra cứu tri thức thực tế liên quan
          </h3>
          <p className="queries-hint">
            Nhấn vào câu hỏi để chuyển thẳng vào RAG Workspace và tìm kiếm bằng chứng trong kho tài liệu:
          </p>
          <div className="hotspot-query-list">
            {hotspot.sampleQueries.map((query, index) => (
              <button
                key={index}
                type="button"
                className="hotspot-query-btn"
                onClick={() => onRunRagQuery(query)}
              >
                <span>{query}</span>
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
        </div>

        <div className="hotspot-disclaimer">
          <Info size={13} />
          <span>
            Lưu ý: Mô hình 3D trên mang tính trực quan hóa kiến trúc kỹ thuật. Quá trình RAG truy xuất hoàn toàn từ các tài liệu PDF pháp lý và kỹ thuật chính thức.
          </span>
        </div>
      </div>

      <div className="hotspot-panel-footer">
        <button type="button" className="btn-secondary" onClick={onClose}>
          Về góc nhìn toàn cảnh
        </button>
        <button type="button" className="btn-primary" onClick={onOpenWorkspace}>
          Vào RAG Workspace <ArrowRight size={15} />
        </button>
      </div>
    </div>
  )
}
