import { BookOpenText, PanelLeftClose, Search, Waves } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { Brand } from './Brand'
import { ServiceBadge } from './ServiceBadge'

export function AppShell() {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-top">
          <Brand />
          <button className="icon-button sidebar-collapse" aria-label="Thu gọn thanh điều hướng">
            <PanelLeftClose size={18} />
          </button>
        </div>
        <nav className="side-nav" aria-label="Điều hướng ứng dụng">
          <NavLink to="/workspace"><Search size={18} /><span>Evidence Search</span></NavLink>
          <NavLink to="/documents"><BookOpenText size={18} /><span>Kho tài liệu</span></NavLink>
        </nav>
        <div className="sidebar-note">
          <Waves size={18} />
          <p><strong>Không sinh câu trả lời</strong><br />Kết quả là bằng chứng được truy xuất trực tiếp từ corpus.</p>
        </div>
        <ServiceBadge showMethod />
      </aside>
      <main className="app-main"><Outlet /></main>
    </div>
  )
}
