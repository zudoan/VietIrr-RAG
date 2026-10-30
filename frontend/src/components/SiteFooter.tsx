import { Github, MoveUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from './Brand'

export function SiteFooter() {
  const sourceRepositoryUrl = import.meta.env.VITE_SOURCE_REPOSITORY_URL?.trim()

  return (
    <footer className="site-footer">
      <div className="footer-lead">
        <Brand />
        <p>Workspace nghiên cứu truy xuất bằng chứng cho tài liệu thủy lợi tiếng Việt dài, có cấu trúc và nhiều trang.</p>
      </div>
      <div className="footer-links">
        <Link to="/report">Báo cáo nghiên cứu <MoveUpRight size={14} /></Link>
        <Link to="/demo">Evidence Search <MoveUpRight size={14} /></Link>
        {sourceRepositoryUrl && <a href={sourceRepositoryUrl} target="_blank" rel="noreferrer"><Github size={14} /> Source repository</a>}
      </div>
      <div className="footer-fineprint">
        <span>VietIrr-RAG · 2026</span>
        <span>Không công bố Candidate Test hoặc PDF chưa rõ quyền tái phân phối.</span>
      </div>
    </footer>
  )
}
