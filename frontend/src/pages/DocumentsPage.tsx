import { ExternalLink, FileText, Filter, LoaderCircle, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { DocumentListResponse, DocumentRecord } from '../types'

export function DocumentsPage() {
  const [data, setData] = useState<DocumentListResponse | null>(null)
  const [query, setQuery] = useState('')
  const [type, setType] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<DocumentRecord | null>(null)

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setLoading(true)
      api.documents(query, type).then(setData).catch((reason) => setError(reason.message)).finally(() => setLoading(false))
    }, 180)
    return () => window.clearTimeout(timeout)
  }, [query, type])

  async function openDocument(item: DocumentRecord) {
    try { setSelected(await api.document(item.doc_id)) }
    catch { setSelected(item) }
  }

  return (
    <div className="documents-page">
      <header className="documents-header">
        <div><p className="page-kicker">Source registry</p><h1>Kho tài liệu</h1>
          <p>Duyệt metadata thực, provenance và PDF cục bộ trong VietIrrDocBench.</p></div>
        <div className="document-count"><strong>{data?.total ?? '—'}</strong><span>tài liệu phù hợp</span></div>
      </header>
      <div className="document-toolbar">
        <label><Search size={17} /><span className="sr-only">Tìm tài liệu</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tên, cơ quan, mã tài liệu…" /></label>
        <label><Filter size={17} /><span className="sr-only">Lọc loại tài liệu</span>
          <select value={type} onChange={(event) => setType(event.target.value)}><option value="">Tất cả loại tài liệu</option>
            {data?.types.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
      </div>
      {loading && <div className="document-loading"><LoaderCircle className="spin" /> Đang đọc metadata…</div>}
      {error && <div className="error-state">{error}</div>}
      {!loading && data && <div className="document-grid">
        {data.items.map((item) => <button className="document-card" key={item.doc_id} onClick={() => openDocument(item)}>
          <div className="document-card-top"><span>{item.doc_type}</span><FileText size={19} /></div>
          <h2>{item.title}</h2>
          <p>{item.source_agency}</p>
          <div className="document-tags"><span>{item.publication_date || 'Không rõ ngày'}</span><span>{item.page_count ?? '—'} trang</span></div>
          <footer><span className={item.pdf_available ? 'available' : ''}>{item.pdf_available ? 'PDF khả dụng' : 'Chỉ metadata'}</span><ExternalLink size={15} /></footer>
        </button>)}
      </div>}

      {selected && <div className="document-drawer-backdrop" onClick={() => setSelected(null)}>
        <aside className="document-drawer" onClick={(event) => event.stopPropagation()}>
          <button className="drawer-close" onClick={() => setSelected(null)} aria-label="Đóng"><X /></button>
          <p className="page-kicker">Document provenance</p><h2>{selected.title}</h2>
          <dl>
            <div><dt>Mã tài liệu</dt><dd className="mono">{selected.doc_id}</dd></div>
            <div><dt>Cơ quan</dt><dd>{selected.source_agency}</dd></div>
            <div><dt>Loại</dt><dd>{selected.doc_type}</dd></div>
            <div><dt>Ngày công bố</dt><dd>{selected.publication_date || 'Không xác định'}</dd></div>
            <div><dt>Số trang</dt><dd>{selected.page_count ?? 'Không xác định'}</dd></div>
            <div><dt>Trạng thái phân phối</dt><dd>{selected.redistribution_status || 'Không xác định'}</dd></div>
          </dl>
          <div className="drawer-tags">{selected.basin.map((item) => <span key={item}>{item}</span>)}</div>
          {selected.regions && selected.regions.length > 0 && <section className="drawer-regions">
            <div className="panel-title"><span>Indexable regions</span><span>{selected.evidence_count} units</span></div>
            {selected.regions.map((region) => <article key={region.evidence_id}>
              <span>{region.unit_type === 'TABLE_REGION' ? 'Bảng' : 'Văn bản'} · trang {region.page_number}</span>
              <p>{region.text}</p>
            </article>)}
          </section>}
          {selected.pdf_available && selected.pdf_url ? <a className="drawer-primary" href={api.absoluteUrl(selected.pdf_url)} target="_blank" rel="noreferrer">Mở PDF <ExternalLink size={15} /></a>
            : <p className="drawer-unavailable">PDF không khả dụng trong workspace; metadata và liên kết nguồn vẫn được giữ nguyên.</p>}
          {selected.source_url && <a className="drawer-secondary" href={selected.source_url} target="_blank" rel="noreferrer">Mở nguồn chính thức <ExternalLink size={14} /></a>}
        </aside>
      </div>}
    </div>
  )
}
