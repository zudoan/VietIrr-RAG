import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Compass,
  Expand,
  Grid,
  Maximize2,
  Minimize2,
  Play,
  RotateCcw,
  Sparkles,
  X,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Scene01Opening } from './scenes/Scene01Opening'
import { Scene02Problem } from './scenes/Scene02Problem'
import { Scene03Solution } from './scenes/Scene03Solution'
import { Scene04Architecture } from './scenes/Scene04Architecture'
import { Scene05LiveDemo } from './scenes/Scene05LiveDemo'
import { Scene06Experiments } from './scenes/Scene06Experiments'
import { Scene07Conclusion } from './scenes/Scene07Conclusion'

interface PresentationEngineProps {
  initialScene?: number
  onGoToApp: (query?: string) => void
}

const SCENE_TITLES = [
  '01 · Mở Đầu & Đề Tài',
  '02 · Bài Toán & Thách Thức',
  '03 · Giải Pháp Evidence-First',
  '04 · Kiến Trúc Pipeline',
  '05 · Trình Diễn Hệ Thống',
  '06 · Kết Quả Thực Nghiệm',
  '07 · Tổng Kết & Q&A',
]

export function PresentationEngine({ initialScene = 0, onGoToApp }: PresentationEngineProps) {
  const [currentScene, setCurrentScene] = useState(initialScene)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showIndexMenu, setShowIndexMenu] = useState(false)
  const [direction, setDirection] = useState(1)

  const totalScenes = SCENE_TITLES.length

  const handleNext = () => {
    if (currentScene < totalScenes - 1) {
      setDirection(1)
      setCurrentScene((prev) => prev + 1)
    }
  }

  const handlePrev = () => {
    if (currentScene > 0) {
      setDirection(-1)
      setCurrentScene((prev) => prev - 1)
    }
  }

  const handleJumpTo = (index: number) => {
    setDirection(index > currentScene ? 1 : -1)
    setCurrentScene(index)
    setShowIndexMenu(false)
  }

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {})
      setIsFullscreen(true)
    } else {
      document.exitFullscreen().catch(() => {})
      setIsFullscreen(false)
    }
  }

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }
      if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {
        e.preventDefault()
        handleNext()
      } else if (e.key === 'ArrowLeft' || e.key === 'Backspace' || e.key === 'PageUp') {
        e.preventDefault()
        handlePrev()
      } else if (e.key === 'f' || e.key === 'F') {
        e.preventDefault()
        toggleFullscreen()
      } else if (e.key === 'Escape') {
        if (showIndexMenu) {
          setShowIndexMenu(false)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentScene, totalScenes, showIndexMenu])

  // Track fullscreen changes
  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement))
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  return (
    <div className={`presentation-container ${isFullscreen ? 'is-fullscreen' : ''}`}>
      {/* Top Progress & Status Bar */}
      <header className="presentation-top-bar">
        <div className="top-left">
          <span className="pres-code font-mono">VIETIRR-RAG · BÁO CÁO HỘI ĐỒNG (16:9)</span>
          <span className="pres-title">{SCENE_TITLES[currentScene]}</span>
        </div>

        {/* Progress tracker dots */}
        <div className="progress-dots-track">
          {SCENE_TITLES.map((title, i) => (
            <button
              key={i}
              type="button"
              className={`progress-dot ${i === currentScene ? 'active' : ''} ${i < currentScene ? 'passed' : ''}`}
              onClick={() => handleJumpTo(i)}
              title={title}
              aria-label={`Chuyển tới slide ${i + 1}: ${title}`}
            />
          ))}
        </div>

        <div className="top-right">
          <button
            type="button"
            className="btn-top-demo"
            onClick={() => onGoToApp()}
            title="Mở RAG Workspace thực tế"
          >
            <Play size={13} />
            <span>Live Demo</span>
          </button>
          <button
            type="button"
            className="btn-icon-top"
            onClick={toggleFullscreen}
            title={isFullscreen ? 'Thoát Toàn Màn Hình' : 'Bật Toàn Màn Hình (F)'}
          >
            {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </header>

      {/* Progress line */}
      <div
        className="top-progress-line"
        style={{ width: `${((currentScene + 1) / totalScenes) * 100}%` }}
      />

      {/* Main Slide Presentation Stage (16:9 Frame) */}
      <main className="presentation-viewport">
        <div className="presentation-16-9-frame">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={currentScene}
              className="slide-motion-wrapper"
              initial={{ opacity: 0, x: direction * 40 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -direction * 40 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            >
              {currentScene === 0 && <Scene01Opening />}
              {currentScene === 1 && <Scene02Problem />}
              {currentScene === 2 && <Scene03Solution />}
              {currentScene === 3 && <Scene04Architecture />}
              {currentScene === 4 && <Scene05LiveDemo onGoToApp={onGoToApp} />}
              {currentScene === 5 && <Scene06Experiments />}
              {currentScene === 6 && <Scene07Conclusion onGoToApp={onGoToApp} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>

      {/* Bottom Floating Presentation Dock */}
      <footer className="presentation-floating-dock">
        <div className="dock-left">
          <button
            type="button"
            className="dock-btn-menu"
            onClick={() => setShowIndexMenu(!showIndexMenu)}
          >
            <Grid size={15} />
            <span>Mục lục ({currentScene + 1}/{totalScenes})</span>
          </button>
        </div>

        <div className="dock-center">
          <button
            type="button"
            className="dock-nav-btn"
            disabled={currentScene === 0}
            onClick={handlePrev}
            aria-label="Slide trước"
          >
            <ChevronLeft size={18} />
            <span>Trước</span>
          </button>

          <span className="dock-scene-counter font-mono">
            {String(currentScene + 1).padStart(2, '0')} / {String(totalScenes).padStart(2, '0')}
          </span>

          <button
            type="button"
            className="dock-nav-btn"
            disabled={currentScene === totalScenes - 1}
            onClick={handleNext}
            aria-label="Slide tiếp theo"
          >
            <span>Tiếp</span>
            <ChevronRight size={18} />
          </button>
        </div>

        <div className="dock-right">
          <span className="keyboard-hint">
            Dùng phím <kbd>→</kbd> <kbd>Space</kbd> để tiến · <kbd>F</kbd> toàn màn hình
          </span>
        </div>
      </footer>

      {/* Slide Index Dropup Menu */}
      {showIndexMenu && (
        <div className="slide-index-overlay" onClick={() => setShowIndexMenu(false)}>
          <div className="slide-index-modal" onClick={(e) => e.stopPropagation()}>
            <div className="index-modal-header">
              <h3>Mục Lục Các Slide Báo Cáo</h3>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setShowIndexMenu(false)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="index-modal-list">
              {SCENE_TITLES.map((title, idx) => (
                <button
                  key={idx}
                  type="button"
                  className={`index-item-btn ${idx === currentScene ? 'active' : ''}`}
                  onClick={() => handleJumpTo(idx)}
                >
                  <span className="index-num font-mono">{String(idx + 1).padStart(2, '0')}</span>
                  <span className="index-title">{title}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
