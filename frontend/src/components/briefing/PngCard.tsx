/**
 * 원본 PNG 카드 (미리보기 + 다운로드 + 라이트박스)
 */
import { useEffect, useState, useCallback } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, Download, ImageIcon, RefreshCw, Maximize2, X, ChevronLeft, ChevronRight } from 'lucide-react'
import { Card, ErrorState, Skeleton } from '../ui'
import { cn } from '../../lib/utils'

// ── 라이트박스 모달 ──────────────────────────────────────────────────────────

function PngLightbox({
  urls,
  label,
  initialPage = 0,
  onClose,
}: {
  urls: string[]
  label: string
  initialPage?: number
  onClose: () => void
}) {
  const [page, setPage] = useState(initialPage)
  const [imgLoaded, setImgLoaded] = useState(false)
  const isMulti = urls.length > 1

  const prev = useCallback(() => setPage((p) => Math.max(0, p - 1)), [])
  const next = useCallback(() => setPage((p) => Math.min(urls.length - 1, p + 1)), [urls.length])

  useEffect(() => {
    setImgLoaded(false)
  }, [page])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, prev, next])

  return (
    <motion.div
      className="fixed inset-0 z-[999] flex items-center justify-center bg-black/85 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
      onClick={onClose}
    >
      {/* 모달 컨테이너 — 클릭 이벤트 버블 차단 */}
      <motion.div
        className="relative flex max-h-[95vh] max-w-[90vw] flex-col items-center"
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ duration: 0.2 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 상단 바 */}
        <div className="mb-3 flex w-full items-center justify-between gap-4 px-1">
          <span className="font-mono text-[12px] font-bold tracking-widest text-white/70 uppercase">
            {label}
            {isMulti && (
              <span className="ml-2 text-white/40">
                {page + 1} / {urls.length}
              </span>
            )}
          </span>
          <div className="flex items-center gap-2">
            <a
              href={urls[page]}
              download={`${label}-p${page + 1}.png`}
              className="inline-flex items-center gap-1.5 rounded-[10px] border border-white/20 bg-white/10 px-2.5 py-1.5 text-xs font-bold text-white/80 hover:bg-white/20"
              onClick={(e) => e.stopPropagation()}
            >
              <Download size={13} />
              다운로드
            </a>
            <button
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-full border border-white/20 bg-white/10 text-white/80 hover:bg-white/25"
            >
              <X size={15} strokeWidth={2.5} />
            </button>
          </div>
        </div>

        {/* 이미지 영역 */}
        <div className="relative flex items-center gap-3">
          {/* 이전 버튼 */}
          {isMulti && (
            <button
              onClick={prev}
              disabled={page === 0}
              className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-full border border-white/20 bg-white/10 text-white/80 hover:bg-white/25 disabled:opacity-25"
            >
              <ChevronLeft size={20} strokeWidth={2.5} />
            </button>
          )}

          {/* PNG 이미지 */}
          <div className="relative overflow-hidden rounded-[16px] shadow-2xl" style={{ maxHeight: '85vh' }}>
            {!imgLoaded && (
              <div className="flex h-64 w-64 items-center justify-center text-white/30">
                <RefreshCw size={24} className="animate-spin" />
              </div>
            )}
            <img
              key={urls[page]}
              src={urls[page]}
              alt={`${label} 리포트${isMulti ? ` (${page + 1}/${urls.length})` : ''}`}
              onLoad={() => setImgLoaded(true)}
              className={cn(
                'block h-auto transition-opacity duration-200',
                'max-h-[85vh] w-auto',
                imgLoaded ? 'opacity-100' : 'opacity-0 h-0 w-0',
              )}
            />
          </div>

          {/* 다음 버튼 */}
          {isMulti && (
            <button
              onClick={next}
              disabled={page === urls.length - 1}
              className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-full border border-white/20 bg-white/10 text-white/80 hover:bg-white/25 disabled:opacity-25"
            >
              <ChevronRight size={20} strokeWidth={2.5} />
            </button>
          )}
        </div>

        {/* 페이지 도트 인디케이터 */}
        {isMulti && (
          <div className="mt-3 flex gap-2">
            {urls.map((_, i) => (
              <button
                key={i}
                onClick={() => setPage(i)}
                className={cn(
                  'h-2 rounded-full transition-all',
                  i === page ? 'w-5 bg-white' : 'w-2 bg-white/35',
                )}
              />
            ))}
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}

// ── 단일 페이지 프레임 (인라인 미리보기용) ──────────────────────────────────

function PngFrame({
  url,
  alt,
  pageLabel,
  onRefresh,
  onExpand,
}: {
  url: string
  alt: string
  pageLabel?: string
  onRefresh: () => void
  onExpand: () => void
}) {
  const [imgLoaded, setImgLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    setImgLoaded(false)
    setImgError(false)
  }, [url])

  return (
    <div
      className="group relative cursor-zoom-in overflow-hidden rounded-[22px] border border-line/80 bg-canvas shadow-[0_22px_60px_rgba(0,0,0,0.38)]"
      onClick={onExpand}
    >
      {pageLabel && (
        <div className="absolute left-3 top-3 z-10 rounded-[8px] border border-line/60 bg-canvas/80 px-2 py-0.5 font-mono text-[11px] font-bold text-greige backdrop-blur-sm">
          {pageLabel}
        </div>
      )}
      {/* 호버 시 확대 아이콘 */}
      <div className="absolute inset-0 z-10 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
        <div className="rounded-full border border-white/30 bg-black/50 p-3 backdrop-blur-sm">
          <Maximize2 size={20} className="text-white" />
        </div>
      </div>
      {!imgLoaded && !imgError && <Skeleton className="aspect-[4/3] w-full" />}
      {imgError ? (
        <div className="p-6">
          <ErrorState
            title="이미지를 불러오지 못했습니다"
            message="원본 PNG 응답에 실패했습니다. 다운로드로 직접 확인하거나 다시 생성해 주세요."
            onRetry={onRefresh}
            retryLabel="다시 생성"
            className="border-0 bg-transparent px-0 py-4"
          />
        </div>
      ) : (
        <motion.img
          key={url}
          src={url}
          alt={alt}
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgError(true)}
          initial={{ opacity: 0 }}
          animate={{ opacity: imgLoaded ? 1 : 0 }}
          transition={{ duration: 0.3 }}
          className={imgLoaded ? 'block w-full' : 'absolute inset-0 h-0 w-0 opacity-0'}
        />
      )}
    </div>
  )
}

// ── PngCard ───────────────────────────────────────────────────────────────────

export function PngCard({
  pngUrl,
  pngUrls,
  slot,
  label,
  onRefresh,
}: {
  pngUrl: string | null
  pngUrls?: string[] | null
  slot: string
  label: string
  onRefresh: () => void
}) {
  const [open, setOpen] = useState(false)
  const [lightbox, setLightbox] = useState<{ page: number } | null>(null)

  const effectiveUrls: string[] =
    pngUrls && pngUrls.length > 0 ? pngUrls : pngUrl ? [pngUrl] : []

  const isMultiPage = effectiveUrls.length > 1
  const primaryUrl = effectiveUrls[0] ?? null

  if (effectiveUrls.length === 0) return null

  const openLightbox = (page = 0) => setLightbox({ page })

  return (
    <>
      {/* 라이트박스 모달 (portal 없이 AnimatePresence로) */}
      <AnimatePresence>
        {lightbox && (
          <PngLightbox
            urls={effectiveUrls}
            label={label}
            initialPage={lightbox.page}
            onClose={() => setLightbox(null)}
          />
        )}
      </AnimatePresence>

      <Card
        className="border-hanwha/25 bg-[#211815]"
        eyebrow="Rendered Artifact"
        title={isMultiPage ? `PNG 리서치 노트 (${effectiveUrls.length}페이지)` : 'PNG 리서치 노트'}
        action={
          <div className="flex items-center gap-2">
            {/* 크게 보기 (라이트박스) */}
            <button
              type="button"
              onClick={() => openLightbox(0)}
              className="inline-flex items-center gap-1.5 rounded-[12px] border border-hanwha/40 bg-hanwha/10 px-3 py-1.5 text-xs font-bold text-hanwha transition-colors hover:bg-hanwha hover:text-canvas"
            >
              <Maximize2 size={13} strokeWidth={2} />
              크게 보기
            </button>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-[12px] border border-line/80 bg-canvas/35 px-3 py-1.5 text-xs font-bold text-greige transition-colors hover:border-hanwha/60 hover:text-hanwha"
            >
              <ChevronDown
                size={14}
                strokeWidth={2}
                className={cn('transition-transform', open && 'rotate-180')}
              />
              {open ? '접기' : '미리보기'}
            </button>
            {primaryUrl && (
              <a
                href={primaryUrl}
                download={`briefing-${slot}.png`}
                className="inline-flex items-center gap-1.5 rounded-[12px] border border-line/60 bg-canvas/35 px-3 py-1.5 text-xs font-bold text-greige transition-colors hover:border-hanwha/60 hover:text-hanwha"
              >
                <Download size={14} strokeWidth={2} />
                다운로드
              </a>
            )}
          </div>
        }
      >
        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="overflow-hidden"
            >
              <div className="space-y-4">
                {effectiveUrls.map((url, idx) => (
                  <PngFrame
                    key={url}
                    url={url}
                    alt={`${label} 시황 리포트 PNG${isMultiPage ? ` (${idx + 1}/${effectiveUrls.length})` : ''}`}
                    pageLabel={isMultiPage ? `P${idx + 1}` : undefined}
                    onRefresh={onRefresh}
                    onExpand={() => openLightbox(idx)}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {!open && (
          <div
            className="flex cursor-zoom-in items-center justify-between gap-3 rounded-[16px] border border-line/70 bg-canvas/35 px-4 py-3 text-xs text-muted transition-colors hover:border-hanwha/30"
            onClick={() => openLightbox(0)}
          >
            <div className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-[12px] border border-blue/25 bg-blue/10 text-blue">
                <ImageIcon size={14} strokeWidth={2} />
              </span>
              <div>
                <div className="font-mono text-[11px] font-extrabold uppercase tracking-[0.12em] text-greige">
                  PNG Ready — 클릭해서 크게 보기
                </div>
                <div>
                  {isMultiPage
                    ? `렌더링 산출물 ${effectiveUrls.length}페이지 생성 완료`
                    : '렌더링 산출물 생성 완료'}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onRefresh() }}
              className="inline-flex items-center gap-1 rounded-[10px] border border-line/70 bg-card-2/50 px-2.5 py-1.5 font-bold text-greige transition-colors hover:border-hanwha/50 hover:text-hanwha"
            >
              <RefreshCw size={12} strokeWidth={2} />
              새로고침
            </button>
          </div>
        )}
      </Card>
    </>
  )
}
