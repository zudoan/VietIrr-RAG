import { ArrowRight, ArrowUpRight, CheckCircle2, CircleAlert, Database, ExternalLink, FileCheck2, Microscope, Waves } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { MetricExplorer } from '../components/MetricExplorer'
import { PipelineDiagram } from '../components/PipelineDiagram'
import { SectionReveal } from '../components/SectionReveal'
import { SiteFooter } from '../components/SiteFooter'
import { SiteHeader } from '../components/SiteHeader'
import { ThreeUITopo } from '../components/ThreeUITopo'
import type { ReportResponse } from '../types'

const number = new Intl.NumberFormat('vi-VN')
const date = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: 'long', year: 'numeric' })

function numeric(value: unknown) {
  return typeof value === 'number' ? number.format(value) : '—'
}

export function ReportPage() {
  const [report, setReport] = useState<ReportResponse | null>(null)
  const [error, setError] = useState('')
  const sourceRepositoryUrl = import.meta.env.VITE_SOURCE_REPOSITORY_URL?.trim()

  useEffect(() => {
    api.report().then(setReport).catch((reason) => setError(reason instanceof Error ? reason.message : 'Không thể tải báo cáo.'))
  }, [])

  const demo = useMemo(() => report?.retrieval.demo_queries?.[0], [report])
  const v4 = report?.datasets.v4_candidate_expansion
  const statuses = v4?.normalized_status_counts || {}
  const v3Counts = report?.datasets.v3_2_frozen.counts || {}
  const v4Corpus = report?.corpus.v4_4 || {}

  return (
    <div className="editorial-site report-site">
      <SiteHeader />
      <main>
        <header className="report-hero">
          <div className="report-title">
            <p className="eyebrow"><span>Báo cáo nghiên cứu</span> Snapshot được kiểm chứng</p>
            <h1>Truy xuất bằng chứng<br />cho tài liệu thủy lợi<br /><em>tiếng Việt dài.</em></h1>
          </div>
          <div className="report-abstract">
            <p className="dropcap">VietIrr-RAG nghiên cứu cách tìm đủ tập bằng chứng khi câu trả lời nằm trong bảng, văn bản hoặc nhiều trang khác nhau—và cách giữ mọi claim có thể truy nguyên.</p>
            <dl>
              <div><dt>Phạm vi metric</dt><dd>V3.2 frozen DEV</dd></div>
              <div><dt>Serving live</dt><dd>BM25 Evidence Search</dd></div>
              <div><dt>Cập nhật</dt><dd>{report?.generated_at ? date.format(new Date(report.generated_at)) : 'Đang tải…'}</dd></div>
            </dl>
          </div>
          <div className="report-edition">R / 01 <span>17.10.2026</span></div>
        </header>

        <nav className="report-toc" aria-label="Mục lục báo cáo">
          <span>Nội dung</span>
          <a href="#problem">01 Bài toán</a>
          <a href="#dataset">02 Dataset</a>
          <a href="#quality">03 Chất lượng</a>
          <a href="#retrieval">04 Retrieval</a>
          <a href="#results">05 Kết quả</a>
          <a href="#demo">06 Demo</a>
          <a href="#limitations">07 Hạn chế</a>
        </nav>

        {error && <div className="report-error"><CircleAlert /><div><strong>Không thể đọc snapshot báo cáo</strong><p>{error}</p></div></div>}

        <section className="report-section report-problem" id="problem">
          <SectionReveal className="report-marker"><span>01</span><p>Bài toán và mục tiêu</p></SectionReveal>
          <SectionReveal className="report-main">
            <p className="kicker">Research question</p>
            <h2>Làm thế nào để retrieval không chỉ tìm “một đoạn có vẻ đúng”, mà thu đủ tập bằng chứng cần thiết?</h2>
            <div className="two-column-copy">
              <p>Tài liệu thủy lợi chứa nhiều bảng, OCR không đồng đều và cấu trúc báo cáo lặp theo kỳ. Một câu hỏi có thể cần ghép số liệu trong bảng với ghi chú ở trang khác; đánh giá single-passage vì thế chưa đủ phản ánh độ khó.</p>
              <p>Đơn vị đánh giá chính là complete-evidence recall: toàn bộ gold evidence phải xuất hiện trong Top-K. Hệ thống cũng theo dõi provenance để người dùng có thể kiểm tra tài liệu, trang và vùng nguồn.</p>
            </div>
            <div className="research-equation"><span>AllRecall@K</span><strong>= mean<sub>q</sub> [ G<sub>q</sub> ⊆ TopK(q) ]</strong><small>Đủ toàn bộ bằng chứng, không chỉ một hit.</small></div>
          </SectionReveal>
          <SectionReveal className="report-aside" delay={0.1}>
            <ThreeUITopo />
            <p>Đường đồng mức là ẩn dụ trực quan cho không gian truy xuất: cùng một truy vấn có thể cắt qua nhiều lớp cấu trúc và nguồn.</p>
          </SectionReveal>
        </section>

        <section className="report-section dataset-section" id="dataset">
          <SectionReveal className="report-marker"><span>02</span><p>Hai phiên bản dữ liệu</p></SectionReveal>
          <div className="report-main full-span">
            <SectionReveal className="section-heading report-heading">
              <div><p className="kicker">Không trộn phạm vi</p></div>
              <h2>V3.2 là dataset frozen để đánh giá.<br />V4.4 là corpus và candidate expansion đang review.</h2>
              <p>Hai phiên bản phục vụ hai mục tiêu khác nhau. Website không dùng metric V3.2 để tuyên bố hiệu quả V4.</p>
            </SectionReveal>
            <div className="dataset-compare">
              <SectionReveal className="dataset-panel verified">
                <header><span>V3.2</span><strong>Frozen evaluation dataset</strong><CheckCircle2 /></header>
                <div className="dataset-number"><strong>{numeric(v3Counts.accepted_total)}</strong><span>QA accepted</span></div>
                <dl>
                  <div><dt>Core</dt><dd>{numeric(v3Counts.core)}</dd></div>
                  <div><dt>Challenge</dt><dd>{numeric(v3Counts.challenge)}</dd></div>
                  <div><dt>DEV</dt><dd>{numeric(v3Counts.dev)}</dd></div>
                  <div><dt>Candidate Test</dt><dd>{report?.datasets.v3_2_frozen.candidate_test || '—'}</dd></div>
                </dl>
                <p>Được dùng cho metric retrieval hiện công bố. DEV là phạm vi đánh giá đang hoạt động.</p>
              </SectionReveal>
              <SectionReveal className="dataset-panel research" delay={0.08}>
                <header><span>V4.4</span><strong>Verified corpus + candidates</strong><Microscope /></header>
                <div className="dataset-number"><strong>{numeric(v4Corpus.pdf_sha256_match)}</strong><span>PDF khớp SHA-256</span></div>
                <dl>
                  <div><dt>Candidate 01–09</dt><dd>{numeric(v4?.records_total)}</dd></div>
                  <div><dt>Machine-supported</dt><dd>{numeric(statuses.CANDIDATE_MACHINE_SUPPORTED)}</dd></div>
                  <div><dt>Review required</dt><dd>{numeric(statuses.REVIEW_REQUIRED)}</dd></div>
                  <div><dt>Human gold</dt><dd>{numeric(v4?.human_gold_true)}</dd></div>
                </dl>
                <p>Đang mở rộng độ phủ và chờ human review. Chưa đủ điều kiện tạo evaluation claim.</p>
              </SectionReveal>
            </div>
          </div>
        </section>

        <section className="report-section quality-section" id="quality">
          <SectionReveal className="report-marker"><span>03</span><p>QA & chất lượng dữ liệu</p></SectionReveal>
          <SectionReveal className="report-main">
            <p className="kicker">Quality ledger</p>
            <h2>Machine-supported không đồng nghĩa với human gold.</h2>
            <p className="report-lead">Candidate V4 được theo dõi theo trạng thái review, quarantine và độ đầy đủ locator. Các bản ghi chưa được xác nhận không đi vào metric.</p>
            <div className="quality-ledger">
              <div><span>Machine-supported</span><strong>{numeric(statuses.CANDIDATE_MACHINE_SUPPORTED)}</strong><i className="quality-machine" /></div>
              <div><span>Review required</span><strong>{numeric(statuses.REVIEW_REQUIRED)}</strong><i className="quality-review" /></div>
              <div><span>Quarantine</span><strong>{numeric(statuses.QUARANTINED)}</strong><i className="quality-quarantine" /></div>
              <div><span>Human gold</span><strong>{numeric(v4?.human_gold_true)}</strong><i /></div>
            </div>
          </SectionReveal>
          <SectionReveal className="report-aside evidence-audit" delay={0.1}>
            <div><FileCheck2 /><span>Evidence locators</span><strong>{numeric(report?.data_quality.candidate_evidence_page_locators)}</strong></div>
            <div><CircleAlert /><span>Thiếu anchor/claim/locator trực tiếp</span><strong>{numeric(report?.data_quality.candidate_evidence_without_anchor_claim_or_locator)}</strong></div>
            <p>{report?.data_quality.evaluation_exclusion_reason || 'Đang tải lý do loại khỏi evaluation.'}</p>
          </SectionReveal>
        </section>

        <section className="report-section retrieval-section" id="retrieval">
          <SectionReveal className="report-marker"><span>04</span><p>Kiến trúc retrieval</p></SectionReveal>
          <div className="report-main full-span">
            <SectionReveal className="section-heading report-heading">
              <div><p className="kicker">System architecture</p></div>
              <h2>Pipeline giữ provenance đi cùng dữ liệu từ đầu đến cuối.</h2>
              <p>Live serving dùng đúng thư viện BM25 hiện có. Không rebuild thuật toán và không quảng cáo phương pháp offline như một endpoint đang hoạt động.</p>
            </SectionReveal>
            <SectionReveal><PipelineDiagram /></SectionReveal>
            <div className="method-ledger">
              <div><span>Live</span><strong>BM25 · V3.2 frozen corpus</strong><p>Truy vấn tùy ý, trả evidence thật.</p></div>
              <div><span>Offline verified</span><strong>E5 · Hybrid RRF · Page→Region</strong><p>Replay deterministic trên {numeric(report?.retrieval.qa_evaluated)} DEV QA.</p></div>
              <div><span>Không có</span><strong>LLM answer generation</strong><p>Giao diện không tạo câu trả lời tổng hợp.</p></div>
            </div>
          </div>
        </section>

        <section className="report-section results-section" id="results">
          <SectionReveal className="report-marker"><span>05</span><p>Baseline & kết quả</p></SectionReveal>
          <SectionReveal className="report-main">
            <p className="kicker">V3.2 frozen DEV only</p>
            <h2>So sánh có kiểm soát, không suy rộng sang V4.</h2>
            {report?.retrieval.metrics ? <MetricExplorer metrics={report.retrieval.metrics} /> : <div className="chart-skeleton" />}
          </SectionReveal>
          <SectionReveal className="report-aside result-note" delay={0.1}>
            <Database />
            <h3>Phương pháp đánh giá</h3>
            <p>{report?.retrieval.scope || 'Đang tải phạm vi đánh giá…'}</p>
            <dl>
              <div><dt>Số QA</dt><dd>{numeric(report?.retrieval.qa_evaluated)}</dd></div>
              <div><dt>Serving live</dt><dd>{report?.retrieval.live_method || '—'}</dd></div>
              <div><dt>Chế độ kiểm tra</dt><dd>{report?.retrieval.mode || '—'}</dd></div>
            </dl>
          </SectionReveal>
        </section>

        <section className="report-section demo-section" id="demo">
          <SectionReveal className="report-marker"><span>06</span><p>Evidence Search demo</p></SectionReveal>
          <SectionReveal className="report-main demo-query">
            <p className="kicker">Verified smoke query</p>
            <blockquote>{typeof demo?.query === 'string' ? demo.query : 'Truy vấn demo đang được tải từ snapshot.'}</blockquote>
            <div className="demo-meta">
              <span>Mẫu kiểm tra <strong>Public smoke</strong></span>
              <span>Kết quả <strong>{typeof demo?.result_count === 'number' ? number.format(demo.result_count) : '—'}</strong></span>
              <span>Latency snapshot <strong>{typeof demo?.latency_ms === 'number' ? `${demo.latency_ms.toFixed(2)} ms` : '—'}</strong></span>
            </div>
            <Link className="button button-primary" to={typeof demo?.query === 'string' ? `/demo?q=${encodeURIComponent(demo.query)}` : '/demo'}>Chạy trên live BM25 <ArrowUpRight size={16} /></Link>
          </SectionReveal>
          <SectionReveal className="report-aside demo-note" delay={0.1}>
            <Waves />
            <h3>Demo trả gì?</h3>
            <p>Evidence ID, tài liệu, trang, điểm retrieval và excerpt khi chính sách truy cập cho phép. Không có answer do LLM tạo.</p>
            <Link to="/documents">Mở registry tài liệu <ArrowRight size={15} /></Link>
          </SectionReveal>
        </section>

        <section className="report-section limitation-section" id="limitations">
          <SectionReveal className="report-marker"><span>07</span><p>Hạn chế & hướng tiếp theo</p></SectionReveal>
          <SectionReveal className="report-main">
            <p className="kicker">Scientific limitations</p>
            <h2>Những điều website chưa tuyên bố.</h2>
            <ol className="limitation-list">
              {(report?.limitations || []).map((item, index) => <li key={item}><span>{String(index + 1).padStart(2, '0')}</span><p>{item}</p></li>)}
            </ol>
          </SectionReveal>
          <SectionReveal className="report-aside next-work" delay={0.1}>
            <h3>Hướng nghiên cứu tiếp theo</h3>
            <p>Hoàn tất human review V4, xây index V4 được kiểm chứng, đánh giá trên tập đủ điều kiện và chỉ khi đó mới cân nhắc serving thêm dense/hybrid.</p>
            {sourceRepositoryUrl && <a href={sourceRepositoryUrl} target="_blank" rel="noreferrer">Xem repository <ExternalLink size={14} /></a>}
          </SectionReveal>
        </section>

        <section className="timeline-section">
          <div className="section-shell compact">
            <SectionReveal className="section-heading">
              <div><span className="section-number">08</span><p className="kicker">Timeline / changelog</p></div>
              <h2>Những mốc đã đạt và phần còn mở.</h2>
            </SectionReveal>
            <div className="research-timeline">
              {(report?.milestones || []).map((item) => <SectionReveal className={`timeline-item status-${item.status}`} key={item.slug}>
                <span>{item.occurred_on ? date.format(new Date(`${item.occurred_on}T00:00:00`)) : 'Tiếp theo'}</span>
                <div><h3>{item.title}</h3><p>{item.summary}</p><small>{item.source_path}</small></div>
              </SectionReveal>)}
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  )
}
