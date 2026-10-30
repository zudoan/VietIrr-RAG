import { Link } from 'react-router-dom'

export function Brand() {
  return (
    <Link className="brand" to="/" aria-label="VietIrr-RAG — Trang dự án">
      <svg className="brand-mark" viewBox="0 0 38 38" aria-hidden="true">
        <path d="M4 24c6-8 11-11 16-11s8 3 14 9" />
        <path d="M4 29c7-6 12-8 17-8 4 0 8 2 13 6" />
        <path d="M19 4c-1 6-5 9-5 13a5 5 0 0 0 10 0c0-4-4-7-5-13Z" />
      </svg>
      <span><strong>VietIrr</strong><small>Evidence-first research</small></span>
    </Link>
  )
}
