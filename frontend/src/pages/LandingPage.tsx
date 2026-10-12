import { ArrowRight, BookOpenText, Database, FileStack, ShieldCheck } from 'lucide-react'
import { motion } from 'motion/react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Brand } from '../components/Brand'
import { SearchComposer } from '../components/SearchComposer'
import { ServiceBadge } from '../components/ServiceBadge'
import type { CorpusStats } from '../types'

const format = new Intl.NumberFormat('vi-VN')
const HydroOrb = lazy(() => import('../components/HydroOrb').then((module) => ({ default: module.HydroOrb })))

export function LandingPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<CorpusStats | null>(null)
  const [statsFailed, setStatsFailed] = useState(false)

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStatsFailed(true))
  }, [])

  function goToSearch(query: string) {
    navigate(`/workspace?q=${encodeURIComponent(query)}`)
  }

  return (
    <div className="landing">
      <header className="landing-nav">
        <Brand />
        <nav aria-label="Điều hướng chính">
          <a href="#capabilities">Năng lực</a>
          <Link to="/documents">Tài liệu</Link>
          <Link className="nav-cta" to="/workspace">Mở workspace <ArrowRight size={15} /></Link>
        </nav>
      </header>

      <main>
        <section className="hero">
          <div className="hero-grid" aria-hidden="true" />
          <motion.div className="hero-copy" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}>
            <div className="eyebrow"><ServiceBadge /> <span>Corpus V3.2 · semantic freeze</span></div>
            <h1>VietIrr<br /><em>Intelligence</em></h1>
            <p className="hero-subtitle">Khám phá tri thức thủy lợi bằng trí tuệ nhân tạo.</p>
            <p className="hero-detail">Tra cứu trực tiếp bằng chứng trong tài liệu thủy lợi Việt Nam — có nguồn, trang và đường dẫn PDF khi khả dụng.</p>
            <SearchComposer large onSubmit={goToSearch} />
            <div className="search-hints"><span>Thử:</span>
              <button onClick={() => goToSearch('quy trình vận hành hồ chứa')}>vận hành hồ chứa</button>
              <button onClick={() => goToSearch('chất lượng nước tháng 4')}>chất lượng nước</button>
            </div>
          </motion.div>
          <motion.div className="hero-visual" initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, delay: 0.1 }}>
            <Suspense fallback={<div className="orb-fallback" role="img" aria-label="Quả cầu tri thức thủy văn" />}>
              <HydroOrb />
            </Suspense>
            <div className="orb-label label-a"><span />{stats ? format.format(stats.evidence_units) : 'Index'} đơn vị bằng chứng</div>
            <div className="orb-label label-b"><span />Nguồn chính thống</div>
            <div className="orb-caption">Hydro knowledge graph <small>live corpus signal</small></div>
          </motion.div>
        </section>

        <section className="stats-band" aria-label="Thống kê corpus thực">
          {stats ? <>
            <div><Database /><strong>{format.format(stats.evidence_units)}</strong><span>đơn vị truy xuất</span></div>
            <div><FileStack /><strong>{format.format(stats.documents)}</strong><span>tài liệu nguồn</span></div>
            <div><BookOpenText /><strong>{format.format(stats.pages)}</strong><span>trang đã lập chỉ mục</span></div>
            <div><ShieldCheck /><strong>{format.format(stats.qa_total)}</strong><span>QA đã chấp nhận</span></div>
          </> : <p className="stats-unavailable">{statsFailed ? 'Không thể tải số liệu corpus — API đang ngoại tuyến.' : 'Đang đọc thống kê corpus…'}</p>}
        </section>

        <section className="capabilities" id="capabilities">
          <div className="section-kicker">Từ câu hỏi đến nguồn gốc</div>
          <div className="capability-heading">
            <h2>Mỗi kết quả đều để lại<br />một đường dẫn kiểm chứng.</h2>
            <p>Không bịa câu trả lời. Workspace hiện vận hành ở chế độ Evidence Search, hiển thị rõ phương pháp retrieval và provenance của từng đoạn.</p>
          </div>
          <div className="capability-grid">
            <article><span>01</span><h3>Truy xuất thật</h3><p>BM25 đọc trực tiếp {stats ? format.format(stats.evidence_units) : 'các'} evidence units từ corpus B1 đã đóng băng.</p></article>
            <article><span>02</span><h3>Provenance rõ</h3><p>Tài liệu, cơ quan, loại nguồn, số trang và điểm liên quan đi cùng mỗi citation.</p></article>
            <article><span>03</span><h3>Kiểm chứng PDF</h3><p>Mở đúng tệp gốc tại trang bằng chứng khi PDF có trong workspace.</p></article>
          </div>
          <Link className="text-link" to="/workspace">Bắt đầu tra cứu <ArrowRight size={17} /></Link>
        </section>
      </main>
    </div>
  )
}
