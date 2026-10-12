import { ArrowUpRight, FileText, Table2 } from 'lucide-react'
import type { Evidence } from '../types'

type Props = { evidence: Evidence; selected: boolean; citation: number; onSelect: () => void }

export function EvidenceCard({ evidence, selected, citation, onSelect }: Props) {
  return (
    <article className={`evidence-card ${selected ? 'is-selected' : ''}`} onClick={onSelect}>
      <button className="evidence-hit" type="button" onClick={onSelect} aria-label={`Mở bằng chứng ${citation}`}>
        <span className="evidence-index">[{citation}]</span>
        <span className="evidence-kind">{evidence.unit_type === 'TABLE_REGION' ? <Table2 size={14} /> : <FileText size={14} />}
          {evidence.unit_type === 'TABLE_REGION' ? 'Bảng' : 'Văn bản'} · trang {evidence.page_number}</span>
        <span className="evidence-score">{Math.round(evidence.relevance * 100)}%</span>
      </button>
      <h3>{evidence.title}</h3>
      <p>{evidence.text}</p>
      <footer><span>{evidence.source_agency}</span><ArrowUpRight size={15} /></footer>
    </article>
  )
}
