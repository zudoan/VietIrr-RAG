import { AlertTriangle, BookOpen, Clock, FileSpreadsheet, Layers, ShieldAlert, Split } from 'lucide-react'

export function Scene02Problem() {
  return (
    <div className="scene-slide scene-problem">
      <div className="scene-header">
        <span className="scene-number">SCENE 02</span>
        <h2 className="scene-title">Thách Thức Đặc Thù Của Tài Liệu Ngành Thủy Lợi</h2>
        <p className="scene-deck">
          Tại sao các mô hình RAG tiêu chuẩn trong tài chính hay thương mại điện tử thất bại trên dữ liệu thủy lợi?
        </p>
      </div>

      <div className="problem-grid-3">
        {/* Challenge 1 */}
        <div className="problem-card">
          <div className="card-icon red">
            <BookOpen size={20} />
          </div>
          <h3>1. Tài liệu rất dài & có cấu trúc</h3>
          <p>
            Văn bản quy hoạch lưu vực sông và quy trình vận hành hồ đập dài từ 50 đến hàng trăm trang.
            Các mô hình Transformer thông thường bị giới hạn 512 tokens và <strong>cắt mất 66% nội dung trang</strong>.
          </p>
          <div className="evidence-badge-metric">
            <span>Trung bình 28 trang / văn bản · 30.382 vùng phân tích</span>
          </div>
        </div>

        {/* Challenge 2 */}
        <div className="problem-card">
          <div className="card-icon amber">
            <FileSpreadsheet size={20} />
          </div>
          <h3>2. Bảng biểu số liệu & OCR Scan</h3>
          <p>
            Hơn 406 bảng biểu số liệu dung tích, lưu lượng, mực nước và các văn bản chỉ đạo dấu mộc đỏ quét scan.
            Trích xuất văn bản phẳng (flat text) làm phá vỡ quan hệ hàng - cột và đơn vị đo lường (m³, triệu m³, m³/s).
          </p>
          <div className="evidence-badge-metric">
            <span>406 Bảng số liệu · Nguy cơ sai lệch đơn vị quan trắc</span>
          </div>
        </div>

        {/* Challenge 3 */}
        <div className="problem-card">
          <div className="card-icon blue">
            <Split size={20} />
          </div>
          <h3>3. Multi-Evidence & Rò rỉ Split</h3>
          <p>
            Một câu hỏi kỹ thuật thường cần đối chiếu đồng thời nhiều trang (ví dụ: so sánh dung tích hồ tại Trang 5
            với quy chuẩn vận hành tại Trang 18). Rò rỉ văn bản cùng họ (document family) làm sai lệch kết quả đánh giá.
          </p>
          <div className="evidence-badge-metric">
            <span>25 QA Multi-Evidence trên DEV · Yêu cầu thu hồi đồng thời</span>
          </div>
        </div>
      </div>

      {/* The Crucial Evaluation Gap */}
      <div className="evaluation-gap-banner">
        <div className="gap-icon">
          <ShieldAlert size={24} />
        </div>
        <div className="gap-text">
          <strong>CẢNH BÁO PHƯƠNG PHÁP LUẬN: LỖ HỔNG CỦA CHỈ SỐ ANYRECALL</strong>
          <p>
            Hầu hết các hệ sinh thái RAG chỉ đo <code>AnyRecall@K</code> (chỉ cần tìm được 1 đoạn văn là tính đúng).
            Trong kỹ thuật thủy lợi, tìm thấy 1 đoạn thông báo mà thiếu bảng thông số đi kèm sẽ dẫn đến tính toán sai lệch công trình.
            Dự án bắt buộc phải đo <code>AllRecall@K</code> (thu hồi đầy đủ 100% tập bằng chứng tối thiểu).
          </p>
        </div>
      </div>
    </div>
  )
}
