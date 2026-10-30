import { ArrowRight, CheckCircle2, Compass, ExternalLink, Play, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PRESET_BENCHMARK_QUERIES } from '../../rag/RagWorkspace'

interface Scene05LiveDemoProps {
  onGoToApp: (query?: string) => void
}

export function Scene05LiveDemo({ onGoToApp }: Scene05LiveDemoProps) {
  return (
    <div className="scene-slide scene-livedemo">
      <div className="scene-header">
        <span className="scene-number">SCENE 05</span>
        <h2 className="scene-title">Trình Diễn Thực Tế Hệ Thống (Live Product Demo)</h2>
        <p className="scene-deck">
          Chuyển đổi trực tiếp sang RAG Workspace để kiểm thử truy xuất trên dữ liệu thực tế. Trạng thái bài thuyết trình được bảo toàn 100%.
        </p>
      </div>

      <div className="demo-bridge-card">
        <div className="bridge-left">
          <div className="bridge-badge">
            <Sparkles size={14} />
            <span>KHÔNG GIAN TRUY XUẤT THẬT (PHASE E WORKING APP)</span>
          </div>

          <h3>Sẵn Sàng Kiểm Thử Trực Tiếp Trên Hội Đồng</h3>
          <p>
            Hệ thống RAG Workspace kết nối trực tiếp với backend FastAPI và chỉ mục BM25/Windowed Cache.
            Quý thầy cô và hội đồng có thể chọn các câu hỏi phức tạp về số liệu hồ chứa hoặc nhập câu hỏi mới bất kỳ.
          </p>

          <div className="demo-action-buttons">
            <button
              type="button"
              className="btn-launch-demo"
              onClick={() => onGoToApp()}
            >
              <Play size={18} />
              <span>BẮT ĐẦU LIVE DEMO TRÊN RAG WORKSPACE</span>
              <ArrowRight size={16} />
            </button>

            <a
              href="/app"
              target="_blank"
              rel="noreferrer"
              className="btn-open-tab"
            >
              <span>Mở trong Tab mới</span>
              <ExternalLink size={14} />
            </a>
          </div>

          <div className="bridge-return-notice">
            <ShieldCheck size={14} className="good" />
            <span>
              Khi chuyển sang giao diện Demo, sẽ luôn có thanh công cụ nổi phía trên: <strong>« Quay lại Slide 05 »</strong> để tiếp tục phần thuyết trình.
            </span>
          </div>
        </div>

        <div className="bridge-right">
          <span className="sample-list-title">
            <Search size={14} />
            <span>Các câu hỏi kiểm thử đề xuất sẵn (1-Click Run):</span>
          </span>

          <div className="bridge-sample-queries">
            {PRESET_BENCHMARK_QUERIES.slice(0, 3).map((item) => (
              <div
                key={item.id}
                className="bridge-query-item"
                onClick={() => onGoToApp(item.query)}
              >
                <div className="query-meta-header">
                  <span className="qid font-mono">{item.id}</span>
                  <span className="qcat">{item.category}</span>
                </div>
                <p className="qtext">{item.query}</p>
                <div className="query-click-run">
                  <span>Chạy thử ngay</span>
                  <ArrowRight size={12} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
