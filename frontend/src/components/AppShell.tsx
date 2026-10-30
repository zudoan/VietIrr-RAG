import { BookOpenText, ExternalLink, Search } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Brand } from './Brand'
import { ServiceBadge } from './ServiceBadge'

export function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Brand />
        <nav className="primary-nav" aria-label="Điều hướng chính">
          <NavLink to="/" end>Dự án</NavLink>
          <NavLink to="/report">Báo cáo nghiên cứu</NavLink>
        </nav>
        <nav className="utility-nav" aria-label="Công cụ nghiên cứu">
          <NavLink to="/demo"><Search size={15} /> Evidence Search</NavLink>
          <NavLink to="/documents"><BookOpenText size={15} /> Tài liệu</NavLink>
        </nav>
      </header>
      <div className="app-context">
        <ServiceBadge showMethod />
        <p>Chỉ truy xuất bằng chứng; không sinh câu trả lời.</p>
        <Link to="/report#limitations">Phạm vi công bố <ExternalLink size={13} /></Link>
      </div>
      <main className="app-main"><Outlet /></main>
    </div>
  )
}
