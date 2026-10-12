import { AlertTriangle, BookMarked, ExternalLink, FileSearch, Gauge, History, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { EvidenceCard } from '../components/EvidenceCard'
import { SearchComposer } from '../components/SearchComposer'
import { ServiceBadge } from '../components/ServiceBadge'
import type { Evidence, SearchResponse } from '../types'

const HISTORY_KEY = 'vietirr-search-history'

function getHistory(): string[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') }
  catch { return [] }
}

export function WorkspacePage() {
  const [params, setParams] = useSearchParams()
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [selected, setSelected] = useState<Evidence | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [history, setHistory] = useState<string[]>(getHistory)
  const initialQuery = params.get('q') || ''

  const runSearch = useCallback(async (query: string) => {
    setLoading(true)
    setError('')
    setParams({ q: query }, { replace: true })
    try {
      const data = await api.search(query)
      setResponse(data)
      setSelected(data.results[0] || null)
      setHistory((current) => {
        const next = [query, ...current.filter((item) => item !== query)].slice(0, 6)
        localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
        return next
      })
    } catch (reason) {
      setResponse(null)
      setSelected(null)
      setError(reason instanceof Error ? reason.message : 'Không thể kết nối dịch vụ retrieval.')
    } finally {
      setLoading(false)
    }
  }, [setParams])

  useEffect(() => {
    if (initialQuery && !response && !loading) void runSearch(initialQuery)
    // URL bootstrap only; runSearch updates the same query parameter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectedNumber = useMemo(() => response?.results.findIndex((item) => item.evidence_id === selected?.evidence_id) ?? -1,
    [response, selected])

  return (
    <div className="workspace">
      <header className="workspace-header">
        <div><p className="page-kicker">Research workspace</p><h1>Evidence Search</h1></div>
        <ServiceBadge showMethod />
      </header>
      <div className="workspace-grid">
        <aside className="history-panel">
          <div className="panel-title"><History size={16} /><span>Gần đây</span></div>
          {history.length ? <ul>{history.map((item) => <li key={item}><button onClick={() => runSearch(item)}>{item}</button></li>)}</ul>
            : <p className="empty-note">Lịch sử trên trình duyệt này sẽ xuất hiện tại đây.</p>}
          <Link to="/documents" className="history-link"><BookMarked size={16} /> Khám phá tài liệu</Link>
        </aside>

        <section className="results-panel">
          <SearchComposer key={initialQuery} initialValue={initialQuery} loading={loading} onSubmit={runSearch} />
          {!response && !loading && !error && <div className="workspace-empty">
            <div className="empty-orbit"><FileSearch size={30} /></div>
            <p className="page-kicker">Grounded retrieval</p>
            <h2>Tìm bằng chứng, không suy diễn.</h2>
            <p>Nhập câu hỏi hoặc chủ đề. Hệ thống sẽ trả về các đoạn nguồn có điểm liên quan cao nhất từ corpus đã đóng băng.</p>
          </div>}
          {loading && <div className="loading-state"><span /><span /><span /><p>Đang truy xuất evidence units…</p></div>}
          {error && <div className="error-state"><AlertTriangle /><div><strong>Không thể tìm kiếm</strong><p>{error}</p></div></div>}
          {response && !loading && <>
            <div className="result-summary">
              <div><span className="mode-label">Evidence Search</span><h2>“{response.query}”</h2></div>
              <p><Gauge size={15} /> {response.result_count} kết quả · {response.latency_ms} ms</p>
            </div>
            <div className="honesty-notice"><AlertTriangle size={15} /><span>{response.answer_notice}</span></div>
            {response.results.length ? <div className="evidence-list">
              {response.results.map((item, index) => <EvidenceCard key={item.evidence_id} evidence={item}
                citation={index + 1} selected={item.evidence_id === selected?.evidence_id} onSelect={() => setSelected(item)} />)}
            </div> : <div className="no-results"><h3>Chưa tìm thấy bằng chứng phù hợp.</h3><p>Thử dùng từ khóa xuất hiện trong tài liệu hoặc rút gọn truy vấn.</p></div>}
          </>}
        </section>

        <AnimatePresence mode="wait">
          <aside className={`evidence-panel ${selected ? 'has-evidence' : ''}`} key={selected?.evidence_id || 'empty'}>
            {selected ? <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}>
              <div className="panel-title"><span>Evidence [{selectedNumber + 1}]</span>
                <button className="mobile-close" onClick={() => setSelected(null)} aria-label="Đóng bằng chứng"><X size={17} /></button></div>
              <div className="evidence-meta">
                <span>{selected.unit_type === 'TABLE_REGION' ? 'Table region' : 'Text region'}</span>
                <strong>{Math.round(selected.relevance * 100)}% liên quan</strong>
              </div>
              <blockquote>{selected.text}</blockquote>
              <dl>
                <div><dt>Tài liệu</dt><dd>{selected.title}</dd></div>
                <div><dt>Cơ quan</dt><dd>{selected.source_agency}</dd></div>
                <div><dt>Trang</dt><dd>{selected.page_number}</dd></div>
                <div><dt>Evidence ID</dt><dd className="mono">{selected.evidence_id}</dd></div>
              </dl>
              <div className="evidence-actions">
                {selected.pdf_available && selected.pdf_url ? <a href={api.absoluteUrl(selected.pdf_url)} target="_blank" rel="noreferrer">
                  Mở PDF · trang {selected.page_number} <ExternalLink size={15} /></a> : <span className="disabled-action">PDF không có trong workspace</span>}
                {selected.source_url && <a className="source-link" href={selected.source_url} target="_blank" rel="noreferrer">Nguồn chính thức <ExternalLink size={14} /></a>}
              </div>
            </motion.div> : <div className="panel-placeholder"><FileSearch size={24} /><p>Chọn một citation để xem đầy đủ provenance và nguồn PDF.</p></div>}
          </aside>
        </AnimatePresence>
      </div>
    </div>
  )
}
