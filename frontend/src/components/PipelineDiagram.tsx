import { ArrowRight } from 'lucide-react'

const nodes = [
  ['01', 'Nguồn chính thức', 'PDF + provenance'],
  ['02', 'Phân tích cấu trúc', 'page · region · table'],
  ['03', 'Evidence units', 'quality-gated corpus'],
  ['04', 'Retrieval', 'BM25 live · V3.2'],
  ['05', 'Kiểm chứng', 'document · page · source'],
]

export function PipelineDiagram() {
  return (
    <div className="pipeline-diagram" role="img" aria-label="Luồng từ PDF chính thức đến kết quả Evidence Search">
      {nodes.map(([index, title, detail], position) => (
        <div className="pipeline-node" key={index}>
          <span>{index}</span><strong>{title}</strong><small>{detail}</small>
          {position < nodes.length - 1 && <ArrowRight aria-hidden="true" />}
        </div>
      ))}
    </div>
  )
}
