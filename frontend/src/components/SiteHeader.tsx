import { ArrowUpRight, Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Brand } from './Brand'

export function SiteHeader() {
  const [open, setOpen] = useState(false)

  return (
    <header className="site-header">
      <Brand />
      <button className="menu-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label="Mở menu">
        {open ? <X /> : <Menu />}
      </button>
      <div className={`site-nav-wrap ${open ? 'is-open' : ''}`}>
        <nav className="primary-nav" aria-label="Điều hướng chính">
          <NavLink to="/" end onClick={() => setOpen(false)}>Dự án</NavLink>
          <NavLink to="/report" onClick={() => setOpen(false)}>Báo cáo nghiên cứu</NavLink>
        </nav>
        <nav className="utility-nav" aria-label="Công cụ">
          <Link to="/documents" onClick={() => setOpen(false)}>Kho tài liệu</Link>
          <Link className="header-cta" to="/demo" onClick={() => setOpen(false)}>Evidence Search <ArrowUpRight size={15} /></Link>
        </nav>
      </div>
    </header>
  )
}
