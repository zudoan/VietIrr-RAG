import { useMemo, useState } from 'react'
import type { MetricValues } from '../types'

const labels: Record<string, string> = {
  bm25: 'BM25',
  e5: 'E5 dense',
  hybrid: 'Hybrid RRF',
  page_region: 'Page → Region',
}

export function MetricExplorer({ metrics }: { metrics: Record<string, MetricValues> }) {
  const methods = Object.keys(metrics)
  const [selected, setSelected] = useState(methods.includes('page_region') ? 'page_region' : methods[0])
  const values = metrics[selected]
  const bars = useMemo(() => values ? [
    ['Any R@10', values['10'].any_recall],
    ['All R@20', values['20'].all_recall],
    ['MRR', values.mrr],
    ['nDCG@10', values['ndcg@10']],
  ] as const : [], [values])

  if (!values) return <p className="data-unavailable">Metric chưa khả dụng từ API.</p>

  return (
    <div className="metric-explorer">
      <div className="metric-tabs" role="tablist" aria-label="Chọn phương pháp retrieval">
        {methods.map((method) => <button key={method} role="tab" aria-selected={selected === method} onClick={() => setSelected(method)}>{labels[method] || method}</button>)}
      </div>
      <div className="metric-chart">
        {bars.map(([label, value]) => <div className="metric-row" key={label}>
          <span>{label}</span>
          <div><i style={{ width: `${Math.max(value * 100, 1)}%` }} /></div>
          <strong>{value.toFixed(4)}</strong>
        </div>)}
      </div>
      <p className="metric-caption">V3.2 frozen DEV · n={values.sample_count}. Chiều dài thanh biểu diễn giá trị trong miền 0–1.</p>
    </div>
  )
}
