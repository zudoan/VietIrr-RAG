import { CheckCircle2, Database, EyeOff, FileCheck2, Link2, Scale, ShieldCheck } from 'lucide-react'

export function Scene03Solution() {
  return (
    <div className="scene-slide scene-solution">
      <div className="scene-header">
        <span className="scene-number">SCENE 03</span>
        <h2 className="scene-title">Giải Pháp Đề Xuất: Evidence-First Retrieval</h2>
        <p className="scene-deck">
          Chuyển dịch trọng tâm từ việc sinh câu trả lời tự do sang việc truy xuất đủ tập bằng chứng có khả năng kiểm chứng.
        </p>
      </div>

      <div className="solution-pillars-grid">
        {/* Pillar 1 */}
        <div className="solution-pillar-card">
          <div className="pillar-top">
            <span className="pillar-num">01</span>
            <FileCheck2 size={24} className="pillar-icon" />
          </div>
          <h3>Tính Truy Nguyên Tuyệt Đối (Provenance)</h3>
          <p>
            Mỗi kết quả trả về bắt buộc gắn liền với <strong>Mã tài liệu</strong>, <strong>Số trang chính xác</strong>,{' '}
            <strong>Evidence ID</strong> và <strong>Mã băm SHA-256</strong> của tài liệu gốc. Không một luận điểm nào được đưa ra mà không có bằng chứng đối chiếu.
          </p>
          <ul className="pillar-list">
            <li><CheckCircle2 size={13} /> Link trực tiếp đến đúng trang trong file PDF</li>
            <li><CheckCircle2 size={13} /> Không sửa đổi hay paraphrase làm méo mó số liệu</li>
          </ul>
        </div>

        {/* Pillar 2 */}
        <div className="solution-pillar-card highlight">
          <div className="pillar-top">
            <span className="pillar-num">02</span>
            <Scale size={24} className="pillar-icon gold" />
          </div>
          <h3>Thu Hồi Đủ Tập Bằng Chứng (MSES)</h3>
          <p>
            Định nghĩa đơn vị thành công là <strong>Minimal Sufficient Evidence Set (MSES)</strong>:
            Tập bằng chứng nhỏ nhất nhưng đủ để một kỹ sư thủy lợi đưa ra kết luận kỹ thuật mà không cần phỏng đoán.
          </p>
          <div className="formula-box font-mono">
            AllRecall@K = (1/N) * ∑ 𝟙[ G_q ⊆ TopK(q) ]
          </div>
        </div>

        {/* Pillar 3 */}
        <div className="solution-pillar-card">
          <div className="pillar-top">
            <span className="pillar-num">03</span>
            <EyeOff size={24} className="pillar-icon" />
          </div>
          <h3>Local LLM & Citation Guard</h3>
          <p>
            Tích hợp mô hình ngôn ngữ <strong>Qwen2.5:7B</strong> chạy GPU nội bộ kèm tầng kiểm chứng{' '}
            <strong>Citation Guard</strong>. Mỗi câu trả lời phải có trích dẫn trang cụ thể; khi thiếu bằng chứng, hệ thống chủ động kích hoạt cơ chế an toàn từ chối (Fail-closed).
          </p>
          <ul className="pillar-list">
            <li><CheckCircle2 size={13} /> Chặn đứng hallucination số liệu bảng biểu</li>
            <li><CheckCircle2 size={13} /> Mở PDF Viewer trực tiếp tại đúng trang trích dẫn</li>
          </ul>
        </div>
      </div>

      {/* Dataset V4 Stat Pills */}
      <div className="dataset-recap-bar">
        <span className="recap-title">Tập Dữ Liệu Vận Hành (Corpus V4_R6_FROZEN):</span>
        <div className="recap-items">
          <span className="recap-pill"><strong>93</strong> Tài liệu PDF</span>
          <span className="recap-pill"><strong>2.578</strong> Trang</span>
          <span className="recap-pill"><strong>27.144</strong> Evidence Units</span>
          <span className="recap-pill"><strong>DEV-93</strong> Benchmark</span>
          <span className="recap-pill leak-zero"><strong>0.00%</strong> Leakage (Train/Dev)</span>
        </div>
      </div>
    </div>
  )
}
