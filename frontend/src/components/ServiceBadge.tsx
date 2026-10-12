import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ServiceStatus } from '../types'

export function ServiceBadge({ showMethod = false }: { showMethod?: boolean }) {
  const [status, setStatus] = useState<ServiceStatus | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    api.health().then(setStatus).catch(() => setFailed(true))
  }, [])

  return (
    <div className={`service-badge ${status ? 'is-online' : ''} ${failed ? 'is-offline' : ''}`}
      title={status?.retrieval_method || 'Đang kiểm tra dịch vụ'}>
      <span className="status-dot" />
      <span>{status ? (showMethod ? 'BM25 · corpus thật' : 'API sẵn sàng') : failed ? 'API ngoại tuyến' : 'Đang kết nối'}</span>
    </div>
  )
}
