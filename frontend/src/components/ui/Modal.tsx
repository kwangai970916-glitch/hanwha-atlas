/**
 * Modal — 재사용 웜다크 글래스 팝업
 * React portal + framer-motion AnimatePresence + ESC/백드롭/X 닫기 + body scroll lock
 */
import { useEffect, useCallback, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

export type ModalProps = {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children?: ReactNode
  /** max-width 클래스 (기본: max-w-3xl) */
  maxWidth?: string
}

/** 백드롭 클릭 — 자식 클릭 버블 차단 */
function stop(e: React.MouseEvent) {
  e.stopPropagation()
}

export function Modal({ open, onClose, title, children, maxWidth = 'max-w-3xl' }: ModalProps) {
  // ESC 키 닫기
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose],
  )

  // body scroll lock + ESC 리스너
  useEffect(() => {
    if (!open) return
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKey)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', handleKey)
    }
  }, [open, handleKey])

  return createPortal(
    <AnimatePresence>
      {open && (
        /* ── 백드롭 ── */
        <motion.div
          key="modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
          style={{ background: 'rgba(20,14,12,0.72)' }}
          aria-modal="true"
          role="dialog"
        >
          {/* ── 모달 패널 ── */}
          <motion.div
            key="modal-panel"
            initial={{ opacity: 0, scale: 0.94, y: 18 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 18 }}
            transition={{ type: 'spring', stiffness: 300, damping: 28 }}
            onClick={stop}
            className={cn(
              'relative flex max-h-[90vh] w-full flex-col',
              'overflow-hidden rounded-card border border-line bg-card shadow-card',
              maxWidth,
            )}
          >
            {/* 상단 오렌지 hairline */}
            <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-hanwha to-transparent opacity-70" />

            {/* 헤더 */}
            {title && (
              <header className="flex shrink-0 items-center justify-between gap-4 border-b border-line px-5 py-4">
                <div className="min-w-0 font-display text-base font-bold tracking-tight text-beige">
                  {title}
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="닫기"
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-chip text-muted transition-colors hover:bg-card-2 hover:text-beige"
                >
                  <X size={16} strokeWidth={2} />
                </button>
              </header>
            )}

            {/* X 버튼 (title 없을 때) */}
            {!title && (
              <button
                type="button"
                onClick={onClose}
                aria-label="닫기"
                className="absolute right-4 top-4 z-10 grid h-7 w-7 shrink-0 place-items-center rounded-chip text-muted transition-colors hover:bg-card-2 hover:text-beige"
              >
                <X size={16} strokeWidth={2} />
              </button>
            )}

            {/* 스크롤 가능한 본문 */}
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

export default Modal
