import { AlertCircle, BarChart3, CheckCircle2, ChevronRight, Info, TrendingUp, Trophy } from 'lucide-react'
import { useState } from 'react'

export function Scene06Experiments() {
  const [activeTab, setActiveTab] = useState<'r6_frozen' | 'b2_baseline' | 'p2_windowing' | 'negative_results'>('r6_frozen')

  return (
    <div className="scene-slide scene-experiments">
      <div className="scene-header">
        <span className="scene-number">SCENE 06</span>
        <h2 className="scene-title">Kết Quả Thực Nghiệm & Đánh Giá Độc Lập</h2>
        <p className="scene-deck">
          Báo cáo số liệu trung thực dựa trên tập dữ liệu kiểm thử chuẩn DEV (n=93) và pipeline vận hành R6 Frozen.
        </p>
      </div>

      {/* Tabs navigation */}
      <div className="experiments-tabs-bar">
        <button
          type="button"
          className={`exp-tab-btn ${activeTab === 'r6_frozen' ? 'active' : ''}`}
          onClick={() => setActiveTab('r6_frozen')}
        >
          <Trophy size={14} />
          <span>R6 Frozen Pipeline (Vận Hành V4 - DEV-93)</span>
        </button>
        <button
          type="button"
          className={`exp-tab-btn ${activeTab === 'p2_windowing' ? 'active' : ''}`}
          onClick={() => setActiveTab('p2_windowing')}
        >
          <BarChart3 size={14} />
          <span>Nghiên Cứu Lịch Sử P2: Windowing (V3.2)</span>
        </button>
        <button
          type="button"
          className={`exp-tab-btn ${activeTab === 'b2_baseline' ? 'active' : ''}`}
          onClick={() => setActiveTab('b2_baseline')}
        >
          <BarChart3 size={14} />
          <span>Ablation Baselines (BM25 vs Dense)</span>
        </button>
        <button
          type="button"
          className={`exp-tab-btn ${activeTab === 'negative_results' ? 'active' : ''}`}
          onClick={() => setActiveTab('negative_results')}
        >
          <Info size={14} />
          <span>Bài Học Từ Kết Quả Âm Tính</span>
        </button>
      </div>

      {/* TAB 0: R6 Frozen Hybrid Pipeline */}
      {activeTab === 'r6_frozen' && (
        <div className="tab-pane-content">
          <div className="p2-metrics-hero-grid">
            <div className="metric-box hero-box">
              <span className="box-label">Candidate Hit@100 (DEV-93)</span>
              <strong className="box-val text-flow">91.40%</strong>
              <span className="box-gain">85/93 truy vấn thu hồi đúng tài liệu</span>
              <small>R6 Hybrid Fusion (BM25 + BGE-M3 + Reranker)</small>
            </div>

            <div className="metric-box">
              <span className="box-label">Page Hit@5</span>
              <strong className="box-val text-good">67.74%</strong>
              <span className="box-sub">63/93 truy vấn định vị đúng trang đích</span>
              <small>Ngân sách Top-5 trang tiềm năng</small>
            </div>

            <div className="metric-box">
              <span className="box-label">Evidence Page Hit@5</span>
              <strong className="box-val text-amber">61.29%</strong>
              <span className="box-sub">57/93 truy vấn trích xuất đúng vùng dữ liệu</span>
              <small>MRR = 0.4516 · nDCG@10 = 0.5082</small>
            </div>
          </div>

          <div className="table-wrapper">
            <table className="scientific-table">
              <thead>
                <tr>
                  <th>Chỉ số Kiểm định R6</th>
                  <th>Giá trị Đo lường</th>
                  <th>Tập Đánh giá</th>
                  <th>Phạm vi Bằng chứng</th>
                  <th>Ý nghĩa Kỹ thuật</th>
                </tr>
              </thead>
              <tbody>
                <tr className="highlight-row">
                  <td><strong>Candidate Hit@100</strong></td>
                  <td><strong>91.40% (85/93)</strong></td>
                  <td>DEV-93 (93 câu hỏi)</td>
                  <td>Toàn bộ 93 PDF V4</td>
                  <td>Khả năng thu hồi tài liệu chứa đáp án trong Top 100 ứng viên</td>
                </tr>
                <tr>
                  <td>Page Hit@5</td>
                  <td>67.74% (63/93)</td>
                  <td>DEV-93</td>
                  <td>Top 5 trang tái xếp hạng</td>
                  <td>Tỷ lệ trang đích xuất hiện trong Top 5 sau BGE Reranker</td>
                </tr>
                <tr>
                  <td>Evidence Page Hit@5</td>
                  <td>61.29% (57/93)</td>
                  <td>DEV-93</td>
                  <td>Top 5 Evidence Units</td>
                  <td>Tỷ lệ trích xuất đúng đoạn văn hoặc bảng biểu mang thông số</td>
                </tr>
                <tr>
                  <td>MRR (Mean Reciprocal Rank)</td>
                  <td>0.4516</td>
                  <td>DEV-93</td>
                  <td>Thứ hạng ứng viên đầu tiên</td>
                  <td>Đo lường vị trí trung bình của bằng chứng chuẩn trong kết quả</td>
                </tr>
                <tr>
                  <td>nDCG@10</td>
                  <td>0.5082</td>
                  <td>DEV-93</td>
                  <td>Top 10 xếp hạng tích lũy</td>
                  <td>Đo lường độ tăng ích lũy kế có chiết khấu theo thứ hạng</td>
                </tr>
                <tr>
                  <td>Rò rỉ Phân tách (Leakage)</td>
                  <td>0.00%</td>
                  <td>Train vs DEV-93</td>
                  <td>Phân tách theo họ văn bản</td>
                  <td>Không có tài liệu nào thuộc tập DEV xuất hiện trong huấn luyện</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
      {activeTab === 'p2_windowing' && (
        <div className="tab-pane-content">
          <div className="p2-metrics-hero-grid">
            <div className="metric-box hero-box">
              <span className="box-label">Complete-Page Recall@20</span>
              <strong className="box-val text-flow">0.742</strong>
              <span className="box-gain">+4,1% so với P1 Single-Page (0.701)</span>
              <small>Cấu hình B3_WINDOW_TOP10 (384 tokens / overlap 128)</small>
            </div>

            <div className="metric-box">
              <span className="box-label">Tỷ lệ Cắt Ngắn Token</span>
              <strong className="box-val text-good">0.00%</strong>
              <span className="box-sub">Trước phân đoạn: 66,21% trang bị cắt ngắn</span>
              <small>6.134 cửa sổ trượt, không cửa sổ nào vượt 512 tokens</small>
            </div>

            <div className="metric-box">
              <span className="box-label">Số ca Lỗi Được Phục Hồi</span>
              <strong className="box-val text-amber">+6 QA</strong>
              <span className="box-sub">Thu hồi thành công các bảng biểu dài ở đuôi trang</span>
              <small>So với 2 trường hợp bị suy giảm nhẹ do rank displacement</small>
            </div>
          </div>

          <div className="table-wrapper">
            <table className="scientific-table">
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
                <tr className="highlight-row">
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

      {/* TAB 2: B2 Baseline comparison */}
      {activeTab === 'b2_baseline' && (
        <div className="tab-pane-content">
          <div className="table-wrapper">
            <table className="scientific-table">
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
                <tr className="highlight-row">
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

      {/* TAB 3: Scientific Integrity & Negative Results */}
      {activeTab === 'negative_results' && (
        <div className="tab-pane-content">
          <div className="negative-results-card">
            <h3>Kỷ Luật Khoa Học: Bài Học Từ Thí Nghiệm MASH-ER và MAR-ER</h3>
            <p>
              Trong quá trình nghiên cứu, nhóm đã thử nghiệm hai hướng tiếp cận phức tạp: Multi-view Representation (MASH-ER)
              và Adaptive Relevance Recovery (MAR-ER). Kết quả đem lại một phát hiện khoa học mang tính bản lề:
            </p>
            <div className="discovery-box">
              <strong>PHÁT HIỆN KHOA HỌC: ĐÁNH ĐỔI COVERAGE VÀ RANK DISPLACEMENT</strong>
              <p>
                Mở rộng số lượng ứng viên (Coverage@100 tăng vọt từ 0.77 lên <strong>0.86</strong>) không hề giúp tăng All Recall@20,
                ngược lại làm giảm All Recall@20 từ <strong>0.59 xuống 0.47</strong>! Nguyên nhân: Các ứng viên mới được kéo vào đã
                chiếm chỗ và đẩy các bằng chứng vàng (gold evidence) ra ngoài ngưỡng Top-20.
              </p>
            </div>
            <p className="negative-conclusion">
              Nhóm bảo lưu toàn bộ các kết quả âm tính trong báo cáo để chứng minh tính trung thực khoa học,
              không "cherry-pick" số liệu để tạo cảm giác hệ thống luôn tăng trưởng.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
