import { ArrowDown, ArrowRight, ArrowUpRight, Check, CircleDashed, Database, FileSearch, ShieldAlert } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { PipelineDiagram } from '../components/PipelineDiagram'
import { SectionReveal } from '../components/SectionReveal'
import { SiteFooter } from '../components/SiteFooter'
import { SiteHeader } from '../components/SiteHeader'
import type { CorpusStats, ProjectStage, StageStatus } from '../types'

const BasinTerrain = lazy(() => import('../components/BasinTerrain').then((module) => ({ default: module.BasinTerrain })))
const number = new Intl.NumberFormat('vi-VN')
const date = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })

const statusLabels: Record<StageStatus, string> = {
  completed: 'Đã hoàn thành',
  in_progress: 'Đang thực hiện',
  blocked: 'Đang bị chặn',
  planned: 'Đã lên kế hoạch',
}

function StageIcon({ status }: { status: StageStatus }) {
  if (status === 'completed') return <Check size={14} />
  if (status === 'blocked') return <ShieldAlert size={14} />
  return <CircleDashed size={14} />
}

export function LandingPage() {
  const reducedMotion = useReducedMotion()
  const [stats, setStats] = useState<CorpusStats | null>(null)
  const [stages, setStages] = useState<ProjectStage[]>([])
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    Promise.all([api.stats(), api.stages()])
      .then(([statsResponse, stageResponse]) => {
        setStats(statsResponse)
        setStages(stageResponse.items)
      })
      .catch(() => setFailed(true))
  }, [])

  return (
    <div className="editorial-site">
      <SiteHeader />
      <main>
        <section className="project-hero">
          <motion.div
            className="hero-copy"
            initial={reducedMotion ? false : { opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.72, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="eyebrow"><span>VietIrr-RAG</span> Research workspace · 2026</p>
            <h1>Bằng chứng trước.<br /><em>Câu trả lời sau.</em></h1>
            <p className="hero-deck">Hệ thống truy xuất cho tài liệu thủy lợi tiếng Việt dài, có bảng biểu và bằng chứng phân tán qua nhiều trang.</p>
            <div className="hero-actions">
              <Link className="button button-primary" to="/demo">Mở Evidence Search <ArrowUpRight size={17} /></Link>
              <Link className="button button-quiet" to="/report">Đọc báo cáo nghiên cứu <ArrowRight size={17} /></Link>
            </div>
            <div className="hero-proof">
              <span><i className="live-dot" /> BM25 V3.2 đang phục vụ</span>
              <span>Không sinh answer bằng LLM</span>
              <span>{stats?.verified_at ? `Xác minh ${date.format(new Date(stats.verified_at))}` : failed ? 'API chưa kết nối' : 'Đang đọc snapshot…'}</span>
            </div>
          </motion.div>
          <motion.div
            className="hero-terrain"
            initial={reducedMotion ? false : { opacity: 0, clipPath: 'inset(0 0 100% 0)' }}
            animate={{ opacity: 1, clipPath: 'inset(0 0 0% 0)' }}
            transition={{ duration: 1.05, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
          >
            <Suspense fallback={<div className="terrain-fallback" />}><BasinTerrain /></Suspense>
            <div className="terrain-note"><span>Hình 01</span><p>Địa hình lưu vực được mô phỏng theo ngôn ngữ bản đồ kỹ thuật; không đại diện cho một lưu vực cụ thể.</p></div>
          </motion.div>
          <a className="scroll-cue" href="#project-state">Xem trạng thái dự án <ArrowDown size={15} /></a>
        </section>

        <section className="fact-strip" aria-label="Số liệu corpus V4 đã xác minh">
          <div><span>01 / Corpus live</span><strong>{stats ? number.format(stats.documents) : '93'}</strong><p>tài liệu V4 trong serving corpus</p></div>
          <div><span>02 / Evidence</span><strong>{stats ? number.format(stats.evidence_units) : '27.144'}</strong><p>evidence units có thể truy xuất</p></div>
          <div><span>03 / Dataset</span><strong>{stats ? number.format(stats.qa_total) : '545'}</strong><p>QA benchmark trong DEV-93</p></div>
          <div><span>04 / Live method</span><strong className="word-stat">R6 HYBRID</strong><p>R6 Retrieval + Qwen2.5:7B + Citation Guard</p></div>
        </section>

        <section className="project-intro section-shell">
          <SectionReveal className="section-index"><span>01</span><p>Bài toán</p></SectionReveal>
          <SectionReveal className="intro-statement">
            <p className="kicker">Evidence-first retrieval</p>
            <h2>Một kết quả chỉ có giá trị khi người đọc có thể lần ngược về tài liệu, trang và vùng bằng chứng.</h2>
          </SectionReveal>
          <SectionReveal className="intro-notes" delay={0.08}>
            <p>VietIrr-RAG nghiên cứu retrieval trên tài liệu thủy lợi dài, nơi câu hỏi có thể cần văn bản, bảng biểu hoặc nhiều nguồn cùng lúc. Mục tiêu không phải tạo câu trả lời trơn tru, mà là giảm khoảng cách từ truy vấn đến bằng chứng có thể kiểm chứng.</p>
            <div className="principles">
              <span><Database size={17} /> Corpus có version và checksum</span>
              <span><FileSearch size={17} /> Citation ở mức document · page · region</span>
              <span><ShieldAlert size={17} /> Tách rõ kết quả live và nghiên cứu offline</span>
            </div>
          </SectionReveal>
        </section>

        <section className="pipeline-section">
          <div className="section-shell compact">
            <SectionReveal className="section-heading">
              <div><span className="section-number">02</span><p className="kicker">Luồng kiểm chứng</p></div>
              <h2>Từ PDF chính thức đến evidence có định vị.</h2>
              <p>Serving hiện tại dùng R6 Hybrid Pipeline (BM25 + BGE-M3 + Reranker) trên corpus V4_R6_FROZEN kèm mô hình sinh Qwen2.5:7B và Citation Guard.</p>
            </SectionReveal>
            <SectionReveal delay={0.08}><PipelineDiagram /></SectionReveal>
          </div>
        </section>

        <section className="stage-section section-shell" id="project-state">
          <SectionReveal className="section-heading stage-heading">
            <div><span className="section-number">03</span><p className="kicker">Trạng thái nghiên cứu</p></div>
            <h2>Tiến độ có căn cứ,<br />không tô xanh để trình diễn.</h2>
            <p>Mỗi trạng thái được seed từ snapshot readiness và báo cáo đã kiểm tra. Ngày cập nhật và nguồn được giữ cùng bản ghi.</p>
          </SectionReveal>
          {failed ? <div className="data-error">Không thể đọc trạng thái từ API. Không hiển thị dữ liệu thay thế để tránh tạo claim sai.</div> : (
            <div className="stage-list">
              {stages.map((stage, index) => <SectionReveal className={`stage-row status-${stage.status}`} delay={index * 0.035} key={stage.id}>
                <span className="stage-order">{String(stage.order_index).padStart(2, '0')}</span>
                <div className="stage-name"><h3>{stage.name}</h3><span><StageIcon status={stage.status} /> {statusLabels[stage.status]}</span></div>
                <p>{stage.summary}</p>
                <div className="stage-source"><span>{date.format(new Date(stage.updated_at))}</span><small>{stage.evidence_source}</small></div>
              </SectionReveal>)}
            </div>
          )}
        </section>

        <section className="milestone-callout">
          <SectionReveal className="callout-copy">
            <p className="kicker">Ranh giới khoa học</p>
            <h2>V4 mở rộng độ phủ dữ liệu.<br />Chưa mở rộng quyền tuyên bố.</h2>
            <p>Các batch V4 đang mở rộng candidate, nhưng chưa có bản ghi nào đạt HUMAN_GOLD_VERIFIED. Vì vậy mọi metric đang công bố vẫn thuộc V3.2 frozen DEV.</p>
            <Link to="/report#dataset">Xem phân biệt V3.2 và V4.4 <ArrowRight size={16} /></Link>
          </SectionReveal>
          <div className="callout-figure" aria-hidden="true">
            <div className="water-gate"><span /><span /><span /><i /></div>
            <p>Cửa van / kiểm soát luồng công bố</p>
          </div>
        </section>

        <section className="final-cta section-shell">
          <p className="kicker">Tra cứu có thể kiểm chứng</p>
          <h2>Đặt một câu hỏi.<br />Nhận về đường dẫn đến bằng chứng.</h2>
          <div className="hero-actions">
            <Link className="button button-primary" to="/demo">Mở Evidence Search <ArrowUpRight size={17} /></Link>
            <Link className="button button-quiet" to="/documents">Khám phá metadata tài liệu <ArrowRight size={17} /></Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  )
}
