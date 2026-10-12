import { ArrowUp, LoaderCircle, Search } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'

type Props = {
  initialValue?: string
  placeholder?: string
  loading?: boolean
  large?: boolean
  onSubmit: (query: string) => void
}

export function SearchComposer({ initialValue = '', placeholder = 'Hỏi về nguồn nước, hồ chứa, vận hành…', loading, large, onSubmit }: Props) {
  const [value, setValue] = useState(initialValue)

  function submit(event: FormEvent) {
    event.preventDefault()
    const query = value.trim()
    if (query.length >= 2 && !loading) onSubmit(query)
  }

  return (
    <form className={`search-composer ${large ? 'is-large' : ''}`} onSubmit={submit}>
      <Search className="composer-search" size={large ? 22 : 19} aria-hidden="true" />
      <label className="sr-only" htmlFor={large ? 'hero-query' : 'workspace-query'}>Truy vấn bằng chứng</label>
      <input id={large ? 'hero-query' : 'workspace-query'} value={value}
        onChange={(event) => setValue(event.target.value)} placeholder={placeholder} autoComplete="off" />
      <button type="submit" disabled={value.trim().length < 2 || loading}
        aria-label={loading ? 'Đang tìm kiếm' : 'Tìm bằng chứng'}>
        {loading ? <LoaderCircle className="spin" size={19} /> : <ArrowUp size={19} />}
      </button>
    </form>
  )
}
