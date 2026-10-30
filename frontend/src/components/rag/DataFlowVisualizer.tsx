import { Check, Clock, Cpu } from 'lucide-react'

interface DataFlowVisualizerProps {
  isSearching: boolean
  latencyMs?: number
  resultCount?: number
}

const PIPELINE_STEPS = [
  { id: '1', title: 'Truy vấn NFC', desc: 'Chuẩn hóa tiếng Việt' },
  { id: '2', title: 'Cửa sổ 384/128', desc: 'Sliding Spans' },
  { id: '3', title: 'BM25 + Dense E5', desc: 'Dual Retriever' },
  { id: '4', title: 'RRF Fusion (k=60)', desc: 'Hợp nhất hạng' },
  { id: '5', title: 'Page→Region', desc: 'Định tuyến phân tầng' },
  { id: '6', title: 'Bằng chứng & PDF', desc: 'Số trang + Provenance' },
]

export function DataFlowVisualizer({
  isSearching,
  latencyMs,
  resultCount,
}: DataFlowVisualizerProps) {
  return (
    <div className={`clean-dataflow-bar ${isSearching ? 'is-searching' : ''}`}>
      <div className="dataflow-meta-row">
        <div className="dataflow-title-group">
          <span className="clean-dot" />
          <span className="dataflow-label font-mono">PIPELINE TRUY XUẤT THỰC NGHIỆM</span>
        </div>
        {latencyMs !== undefined && (
          <div className="dataflow-stats font-mono">
            <span>Độ trễ: <strong>{latencyMs.toFixed(1)} ms</strong></span>
            <span className="dot-sep">·</span>
            <span>Kết quả: <strong>{resultCount ?? 0} bằng chứng</strong></span>
          </div>
        )}
      </div>

      <div className="clean-stepper-track">
        {PIPELINE_STEPS.map((step, index) => {
          const isDone = !isSearching
          return (
            <div key={step.id} className="stepper-node-item">
              <div className={`stepper-node ${isDone ? 'done' : 'searching'}`}>
                <span className="step-num">{step.id}</span>
                <span className="step-name">{step.title}</span>
              </div>
              {index < PIPELINE_STEPS.length - 1 && <span className="stepper-line" />}
            </div>
          )
        })}
      </div>
    </div>
  )
}
