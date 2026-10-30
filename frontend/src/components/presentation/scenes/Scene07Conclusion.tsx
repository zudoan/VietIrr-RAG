import { ArrowRight, CheckCircle2, Flag, Heart, HelpCircle, Layers, MessageSquare, ShieldCheck, Sparkles, Trophy } from 'lucide-react'
import { Link } from 'react-router-dom'

interface Scene07ConclusionProps {
  onGoToApp: () => void
}

export function Scene07Conclusion({ onGoToApp }: Scene07ConclusionProps) {
  return (
    <div className="scene-slide scene-conclusion">
      <div className="scene-header">
        <span className="scene-number">SCENE 07</span>
        <h2 className="scene-title">Tổng Kết & Kế Hoạch Nghiên Cứu Tiếp Theo</h2>
        <p className="scene-deck">
          Những đóng góp cốt lõi đã hoàn thành và lộ trình phát triển giai đoạn kế tiếp của đề tài.
        </p>
      </div>

      <div className="conclusion-columns-2">
        {/* Left Column: Contributions */}
        <div className="conclusion-card">
          <div className="card-top">
            <Trophy size={18} className="text-good" />
            <h3>Các Đóng Góp Chính Đã Đạt Được</h3>
          </div>

          <div className="contrib-item">
            <CheckCircle2 size={16} className="text-good" />
            <div>
              <strong>1. Corpus Thủy Lợi V4 & Benchmark DEV-93</strong>
              <p>93 tài liệu PDF, 2.578 trang, 27.144 evidence units, phân tách họ văn bản Train/Dev với 0.00% leakage.</p>
            </div>
          </div>

          <div className="contrib-item">
            <CheckCircle2 size={16} className="text-good" />
            <div>
              <strong>2. Pipeline R6 Frozen Hybrid (BM25 + BGE-M3 + Reranker)</strong>
              <p>Candidate Hit@100 đạt 91,40%, Page Hit@5 đạt 67,74%, Evidence Page Hit@5 đạt 61,29% trên DEV-93.</p>
            </div>
          </div>

          <div className="contrib-item">
            <CheckCircle2 size={16} className="text-good" />
            <div>
              <strong>3. Trợ Lý RAG Qwen2.5:7B + Citation Guard & PDF Viewer</strong>
              <p>Sinh câu trả lời có trích dẫn nguồn đối chiếu, cơ chế Fail-closed an toàn và mở PDF Viewer đúng trang.</p>
            </div>
          </div>
        </div>

        {/* Right Column: Limitations & Next Steps */}
        <div className="conclusion-card">
          <div className="card-top">
            <Flag size={18} className="text-flow" />
            <h3>Giới Hạn Thực Tế & Định Hướng</h3>
          </div>

          <div className="contrib-item">
            <span className="step-num">01</span>
            <div>
              <strong>Chất Lượng OCR Với Bảng Biểu Phức Tạp</strong>
              <p>Các báo cáo scan chất lượng thấp hoặc bảng biểu trộn ô (merged cells) phức tạp cần module chuyên biệt.</p>
            </div>
          </div>

          <div className="contrib-item">
            <span className="step-num">02</span>
            <div>
              <strong>Cơ Chế Fail-Closed Nghiêm Ngặt</strong>
              <p>Citation Guard ưu tiên độ tin cậy; khi tài liệu nguồn thiếu căn cứ, hệ thống chủ động từ chối thay vì đoán mò.</p>
            </div>
          </div>

          <div className="contrib-item">
            <span className="step-num">03</span>
            <div>
              <strong>Ontology Chẩn Đoán Ở Chế Độ Shadow Mode</strong>
              <p>Hoạt động song song sau sinh để phân tích tính nhất quán thực thể và đơn vị đo mà không chặn câu trả lời.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Thank you & Q&A Box */}
      <div className="qa-thankyou-box">
        <div className="thankyou-left">
          <h3>CẢM ƠN QUÝ THẦY CÔ VÀ HỘI ĐỒNG ĐÃ LẮNG NGHE!</h3>
          <p>Dự án sẵn sàng bước vào phiên Hỏi & Đáp (Q&A) và Kiểm tra tương tác trực tiếp.</p>
        </div>

        <div className="thankyou-right">
          <button type="button" className="btn-final-demo" onClick={onGoToApp}>
            <Sparkles size={16} />
            <span>Mở RAG Workspace Trải Nghiệm</span>
            <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
