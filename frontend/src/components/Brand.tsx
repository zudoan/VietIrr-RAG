import { Droplets } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" to="/" aria-label="VietIrr Intelligence — trang chủ">
      <span className="brand-mark"><Droplets size={compact ? 17 : 20} strokeWidth={1.8} /></span>
      <span><strong>VietIrr</strong>{!compact && <small>Intelligence</small>}</span>
    </Link>
  )
}
