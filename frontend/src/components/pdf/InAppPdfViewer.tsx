import {
  AlertCircle,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCw,
  Search,
  ShieldCheck,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import * as pdfjsLib from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import type { Evidence } from '../../types'

// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl

interface InAppPdfViewerProps {
  evidence: Evidence | null
  isOpen: boolean
  onClose: () => void
  initialPage?: number
}

export function InAppPdfViewer({
  evidence,
  isOpen,
  onClose,
  initialPage,
}: InAppPdfViewerProps) {
  const [pdfDoc, setPdfDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [numPages, setNumPages] = useState<number>(1)
  const [scale, setScale] = useState<number>(1.15)
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [isCopied, setIsCopied] = useState<boolean>(false)
  const [isExpanded, setIsExpanded] = useState<boolean>(false)

  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const renderTaskRef = useRef<pdfjsLib.RenderTask | null>(null)

  // Resolve target PDF URL and Page Number from Evidence
  const targetPage = initialPage || evidence?.page_number || 1
  const docId = evidence?.doc_id || ''
  const pdfUrl = docId ? api.absoluteUrl(`/api/v1/documents/${encodeURIComponent(docId)}/pdf`) ?? null : null

  // 1. Load PDF Document when evidence/pdfUrl changes
  useEffect(() => {
    if (!isOpen || !pdfUrl) {
      setPdfDoc(null)
      return
    }

    let isMounted = true
    setIsLoading(true)
    setErrorMsg(null)

    const loadingTask = pdfjsLib.getDocument({
      url: pdfUrl,
      withCredentials: false,
    })

    loadingTask.promise
      .then((doc) => {
        if (!isMounted) return
        setPdfDoc(doc)
        setNumPages(doc.numPages)
        // Clamp target page within document bounds
        const clampedPage = Math.min(Math.max(1, targetPage), doc.numPages)
        setCurrentPage(clampedPage)
        setIsLoading(false)
      })
      .catch((err) => {
        if (!isMounted) return
        console.error('PDF.js loading error:', err)
        setErrorMsg('Không thể tải file PDF gốc từ máy chủ. Tài liệu có thể không có bản số hóa trực tiếp hoặc bị hạn chế bản quyền.')
        setIsLoading(false)
      })

    return () => {
      isMounted = false
      loadingTask.destroy().catch(() => {})
    }
  }, [isOpen, pdfUrl, targetPage])

  // 2. Render Page onto Canvas
  useEffect(() => {
    if (!pdfDoc || !canvasRef.current || isLoading) return

    let isCancelled = false

    // Cancel in-flight render task if user switched pages
    if (renderTaskRef.current) {
      renderTaskRef.current.cancel()
    }

    pdfDoc
      .getPage(currentPage)
      .then((page) => {
        if (isCancelled || !canvasRef.current) return

        const canvas = canvasRef.current
        const context = canvas.getContext('2d', { alpha: false })
        if (!context) return

        const pixelRatio = window.devicePixelRatio || 1
        const viewport = page.getViewport({ scale })

        // Canvas internal resolution adjusted for high-DPI displays
        canvas.width = Math.floor(viewport.width * pixelRatio)
        canvas.height = Math.floor(viewport.height * pixelRatio)
        canvas.style.width = `${Math.floor(viewport.width)}px`
        canvas.style.height = `${Math.floor(viewport.height)}px`

        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
        context.imageSmoothingEnabled = true

        const renderContext = {
          canvasContext: context,
          viewport,
          canvas,
        }

        const renderTask = page.render(renderContext)
        renderTaskRef.current = renderTask

        return renderTask.promise
      })
      .catch((err) => {
        if (err?.name === 'RenderingCancelledException') {
          // Expected cancellation on rapid page change
          return
        }
        console.error('Page render error:', err)
      })

    return () => {
      isCancelled = true
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel()
      }
    }
  }, [pdfDoc, currentPage, scale, isLoading])

  // 3. Keyboard shortcuts (Escape, Arrows)
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      } else if (e.key === 'ArrowRight' || e.key === 'PageDown') {
        e.preventDefault()
        handleNextPage()
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault()
        handlePrevPage()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, currentPage, numPages])

  if (!isOpen || !evidence) return null

  const handlePrevPage = () => {
    setCurrentPage((prev) => Math.max(1, prev - 1))
  }

  const handleNextPage = () => {
    setCurrentPage((prev) => Math.min(numPages, prev + 1))
  }

  const handleJumpToPage = (pageNum: number) => {
    if (pageNum >= 1 && pageNum <= numPages) {
      setCurrentPage(pageNum)
    }
  }

  const handleZoomIn = () => {
    setScale((prev) => Math.min(2.5, prev + 0.2))
  }

  const handleZoomOut = () => {
    setScale((prev) => Math.max(0.6, prev - 0.2))
  }

  const handleResetZoom = () => {
    setScale(1.15)
  }

  const handleCopyCitation = () => {
    const citation = `[Bằng chứng Thủy lợi] ${evidence.title}, ${evidence.source_agency}. Mã bằng chứng: ${evidence.evidence_id}, Trang: ${evidence.page_number}. (VietIrr-RAG Corpus V4_R6_FROZEN)`
    navigator.clipboard.writeText(citation)
    setIsCopied(true)
    setTimeout(() => setIsCopied(false), 2000)
  }

  return (
    <div className="pdf-modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className={`pdf-viewer-shell ${isExpanded ? 'is-expanded' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ─── Top Control Toolbar ─── */}
        <header className="pdf-viewer-toolbar">
          <div className="toolbar-left">
            <BookOpen size={16} className="text-teal" />
            <div className="doc-title-group">
              <span className="doc-filename font-mono">{evidence.doc_id}.pdf</span>
              <span className="doc-page-target">
                Trang bằng chứng: <strong>Trang {evidence.page_number}</strong>
              </span>
            </div>
          </div>

          {/* Page navigation controls */}
          <div className="toolbar-center">
            <button
              type="button"
              className="btn-tool-nav"
              disabled={currentPage <= 1 || isLoading}
              onClick={handlePrevPage}
              title="Trang trước (←)"
            >
              <ChevronLeft size={16} />
            </button>

            <div className="page-counter-group font-mono">
              <input
                type="number"
                min={1}
                max={numPages}
                value={currentPage}
                onChange={(e) => handleJumpToPage(Number(e.target.value))}
                className="page-input"
              />
              <span className="page-total">/ {numPages}</span>
            </div>

            <button
              type="button"
              className="btn-tool-nav"
              disabled={currentPage >= numPages || isLoading}
              onClick={handleNextPage}
              title="Trang tiếp (→)"
            >
              <ChevronRight size={16} />
            </button>

            <div className="toolbar-divider" />

            {/* Zoom Controls */}
            <button
              type="button"
              className="btn-tool-icon"
              onClick={handleZoomOut}
              disabled={scale <= 0.6}
              title="Thu nhỏ (-)"
            >
              <ZoomOut size={15} />
            </button>

            <span className="zoom-level-text font-mono">{Math.round(scale * 100)}%</span>

            <button
              type="button"
              className="btn-tool-icon"
              onClick={handleZoomIn}
              disabled={scale >= 2.5}
              title="Phóng to (+)"
            >
              <ZoomIn size={15} />
            </button>

            <button
              type="button"
              className="btn-tool-text font-mono"
              onClick={handleResetZoom}
              title="Khôi phục kích thước 100%"
            >
              100%
            </button>
          </div>

          <div className="toolbar-right">
            <button
              type="button"
              className="btn-tool-icon"
              onClick={() => setIsExpanded(!isExpanded)}
              title={isExpanded ? 'Thu gọn' : 'Phóng to toàn khung'}
            >
              {isExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            </button>

            <button
              type="button"
              className="btn-tool-close"
              onClick={onClose}
              title="Đóng xem tài liệu (Esc)"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* ─── Main Content Split Body ─── */}
        <div className="pdf-viewer-body">
          {/* Document Canvas Render Stage */}
          <div className="pdf-canvas-stage">
            {isLoading && (
              <div className="pdf-state-box loading">
                <Loader2 size={32} className="spin text-teal" />
                <span>Đang tải và hiển thị trang {currentPage}…</span>
              </div>
            )}

            {errorMsg && (
              <div className="pdf-state-box error">
                <AlertCircle size={32} className="text-amber" />
                <p>{errorMsg}</p>
                <div className="error-actions">
                  <a
                    href={evidence.source_url || `/api/v1/documents/${evidence.doc_id}/pdf`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-source-fallback"
                  >
                    <span>Mở liên kết nguồn ngoài</span>
                    <ExternalLink size={13} />
                  </a>
                </div>
              </div>
            )}

            <div className={`canvas-scroll-wrapper ${isLoading ? 'is-loading' : ''}`}>
              <canvas ref={canvasRef} className="pdf-page-canvas" />
            </div>
          </div>

          {/* Right-Hand Evidence Context Sidebar */}
          <aside className="pdf-evidence-context-sidebar">
            <div className="context-head">
              <span className="context-eyebrow font-mono">BẰNG CHỨNG ĐANG ĐỐI CHIẾU</span>
              <span className="context-match-tag font-mono">
                <ShieldCheck size={12} className="text-emerald" />
                <span>Trang {evidence.page_number} Xác thực</span>
              </span>
            </div>

            <div className="context-meta-box">
              <span className="meta-label">Tài liệu:</span>
              <h4 className="meta-doc-title">{evidence.title}</h4>
              <span className="meta-agency">{evidence.source_agency}</span>
            </div>

            <div className="context-quote-section">
              <div className="quote-header">
                <span className="quote-label font-mono">ĐOẠN TRÍCH XUẤT</span>
                <button
                  type="button"
                  className="btn-copy-quote font-mono"
                  onClick={handleCopyCitation}
                >
                  {isCopied ? <Check size={12} className="text-emerald" /> : <Copy size={12} />}
                  <span>{isCopied ? 'Đã sao chép' : 'Sao chép'}</span>
                </button>
              </div>

              <blockquote className="context-quote-text">
                {evidence.text || 'Trích đoạn dữ liệu đã được xác thực.'}
              </blockquote>
            </div>

            <div className="context-meta-ledger font-mono">
              <div className="ledger-item">
                <span>Evidence ID:</span>
                <strong title={evidence.evidence_id}>{evidence.evidence_id}</strong>
              </div>
              <div className="ledger-item">
                <span>Phân loại vùng:</span>
                <strong>{evidence.unit_type}</strong>
              </div>
              <div className="ledger-item">
                <span>Điểm truy xuất:</span>
                <strong>{evidence.score.toFixed(2)}</strong>
              </div>
              <div className="ledger-item">
                <span>Độ liên quan:</span>
                <strong>{(evidence.relevance * 100).toFixed(1)}%</strong>
              </div>
            </div>

            <div className="context-quick-jump">
              <button
                type="button"
                className="btn-jump-evidence-page"
                onClick={() => handleJumpToPage(evidence.page_number)}
              >
                <span>Nhảy tới trang bằng chứng ({evidence.page_number})</span>
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
