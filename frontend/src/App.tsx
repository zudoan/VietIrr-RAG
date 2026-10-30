import { AnimatePresence, motion } from 'motion/react'
import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

const HydraulicAppPage = lazy(() => import('./pages/HydraulicAppPage').then((m) => ({ default: m.HydraulicAppPage })))
const PresentationPage = lazy(() => import('./pages/PresentationPage').then((m) => ({ default: m.PresentationPage })))
const ReportPage = lazy(() => import('./pages/ReportPage').then((m) => ({ default: m.ReportPage })))

function LoadingRoute() {
  return (
    <div className="route-loading">
      <span />
      <span>Đang tải Không gian Thủy lợi Trực quan…</span>
    </div>
  )
}

export default function App() {
  const location = useLocation()

  return (
    <Suspense fallback={<LoadingRoute />}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={location.pathname.startsWith('/presentation') ? 'presentation' : 'app'}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        >
          <Routes location={location}>
            {/* Primary Page 01: Hydraulic RAG System */}
            <Route path="/app" element={<HydraulicAppPage />} />
            <Route path="/" element={<HydraulicAppPage />} />

            {/* Primary Page 02: Cinematic Fullscreen Defense Presentation */}
            <Route path="/presentation" element={<PresentationPage />} />

            {/* Scientific report & legacy report redirect */}
            <Route path="/report" element={<Navigate to="/presentation" replace />} />

            {/* Legacy route redirects to preserve backward compatibility */}
            <Route path="/demo" element={<Navigate to="/app?view=workspace" replace />} />
            <Route path="/workspace" element={<Navigate to="/app?view=workspace" replace />} />
            <Route path="/documents" element={<Navigate to="/app?view=workspace" replace />} />

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Routes>
        </motion.div>
      </AnimatePresence>
    </Suspense>
  )
}
