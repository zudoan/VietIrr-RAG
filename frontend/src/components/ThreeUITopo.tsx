import { lazy, Suspense, useEffect, useRef, useState } from 'react'

const TopoField = lazy(() => import('@designcodeio/threeui/components/TopoField').then((module) => ({ default: module.TopoField })))

export function ThreeUITopo() {
  const host = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(false)

  useEffect(() => {
    if (!host.current) return
    const observer = new IntersectionObserver(([entry]) => setActive(entry.isIntersecting), { rootMargin: '160px' })
    observer.observe(host.current)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={host} className="threeui-topo" aria-label="Trường đường đồng mức tương tác">
      {active ? (
        <Suspense fallback={<div className="topo-fallback" />}>
          <TopoField mode="light" speed={0.24} density={0.8} length={1.15} opacity={0.68} />
        </Suspense>
      ) : <div className="topo-fallback" />}
      <span>ThreeUI Community · Topo Field · MIT</span>
    </div>
  )
}
