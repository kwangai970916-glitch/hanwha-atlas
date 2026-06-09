import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Clock3, History, ImageIcon, RefreshCw, XCircle } from 'lucide-react'
import { Badge, EmptyState, ErrorState, Modal, Skeleton } from '../ui'
import { cn } from '../../lib/utils'
import { formatTs, hasText, SLOT_LABEL } from './utils'
import type { HistoryItem } from './types'

const SLOT_ORDER = ['premarket', 'intraday', 'close'] as const

function recordPngUrl(apiBase: string, idx: number) {
  return `${apiBase}/api/briefing/record-png?idx=${idx}`
}

function HistoryModal({ item, idx, apiBase, onClose }: { item: HistoryItem; idx: number; apiBase: string; onClose: () => void }) {
  const pngUrl = recordPngUrl(apiBase, idx)
  const [imgLoaded, setImgLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)
  const slotLabel = SLOT_LABEL[item.slot ?? ''] ?? item.slot ?? '브리핑'
  const ts = formatTs(item.ts)
  const ok = item.success !== false

  return (
    <Modal
      open
      onClose={onClose}
      maxWidth="max-w-5xl"
      title={
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-base font-bold text-beige">{slotLabel} 리포트</span>
          <Badge tone={ok ? 'blue' : 'down'} className="text-[11px]">{ok ? '성공' : '실패'}</Badge>
          <span className="font-mono text-xs tabular-nums text-muted">{ts}</span>
        </div>
      }
    >
      <div className="space-y-4">
        {hasText(item.decision_summary ?? undefined) && (
          <div className="rounded-chip border border-line bg-card-2/40 px-4 py-3">
            <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-hanwha">Summary</div>
            <p className="text-sm leading-relaxed text-greige">{item.decision_summary}</p>
          </div>
        )}
        <div className="relative overflow-hidden rounded-card border border-line bg-canvas">
          {!imgLoaded && !imgError && <Skeleton className="aspect-[4/3] w-full" />}
          {imgError ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <ImageIcon size={28} strokeWidth={1.5} className="text-muted" />
              <p className="text-sm text-muted">PNG를 불러오지 못했습니다.</p>
            </div>
          ) : (
            <img
              src={pngUrl}
              alt={`${slotLabel} ${ts} 시황 리포트 PNG`}
              onLoad={() => setImgLoaded(true)}
              onError={() => setImgError(true)}
              className={cn('w-full transition-opacity duration-300', imgLoaded ? 'opacity-100' : 'opacity-0 absolute inset-0 h-0')}
            />
          )}
        </div>
      </div>
    </Modal>
  )
}

function LatestCard({ item, idx, apiBase, onOpen }: { item?: HistoryItem; idx?: number; apiBase: string; onOpen: (item: HistoryItem, idx: number) => void }) {
  const slot = item?.slot ?? ''
  const slotLabel = SLOT_LABEL[slot] ?? slot ?? '브리핑'
  const ok = item?.success !== false
  return (
    <button
      type="button"
      disabled={!item || idx == null}
      onClick={() => item && idx != null && onOpen(item, idx)}
      className={cn(
        'group relative overflow-hidden rounded-card border p-4 text-left shadow-card transition-all',
        item ? 'border-line bg-card hover:border-hanwha/45 hover:bg-card-2' : 'cursor-default border-line/70 bg-card/55 opacity-70',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-display text-lg font-black text-beige">{slotLabel}</p>
          <p className="mt-1 font-mono text-[11px] tabular-nums text-muted">{item ? formatTs(item.ts) : '생성 이력 없음'}</p>
        </div>
        {item && <Badge tone={ok ? 'blue' : 'down'}>{ok ? '최신' : '실패'}</Badge>}
      </div>
      {item?.decision_summary ? (
        <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-greige">{item.decision_summary}</p>
      ) : (
        <p className="mt-3 text-sm leading-relaxed text-muted">아직 생성된 {slotLabel}이 없습니다.</p>
      )}
      {item && (
        <div className="mt-4 flex items-center gap-2 text-xs font-semibold text-hanwha opacity-80 group-hover:opacity-100">
          <ImageIcon size={14} /> 클릭해서 확대 보기
        </div>
      )}
      {item && <img src={recordPngUrl(apiBase, idx ?? 0)} alt="" className="pointer-events-none absolute -right-10 -bottom-12 w-36 rotate-[-5deg] rounded-[10px] border border-line/50 opacity-10 transition-opacity group-hover:opacity-20" />}
    </button>
  )
}

function HistoryRow({ item, idx, onOpen }: { item: HistoryItem; idx: number; onOpen: (item: HistoryItem, idx: number) => void }) {
  const ok = item.success !== false
  return (
    <button
      type="button"
      onClick={() => onOpen(item, idx)}
      className="w-full rounded-chip border border-line bg-card-2/40 px-3 py-2.5 text-left transition-colors hover:border-hanwha/40 hover:bg-card-2/70"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5">
          <Badge tone={ok ? 'blue' : 'down'} className="px-1.5 py-0 text-[9px]">{SLOT_LABEL[item.slot ?? ''] ?? item.slot ?? '브리핑'}</Badge>
        </span>
        <span className="inline-flex items-center gap-1 font-mono text-[10px] tabular-nums text-muted">
          {ok ? <CheckCircle2 size={11} className="text-up" /> : <XCircle size={11} className="text-down" />}
          {formatTs(item.ts)}
        </span>
      </div>
      {hasText(item.decision_summary ?? undefined) && <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-greige">{item.decision_summary}</p>}
    </button>
  )
}

export function HistoryRail({ apiBase, refreshKey }: { apiBase: string; refreshKey?: string | null }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [modalState, setModalState] = useState<{ item: HistoryItem; idx: number } | null>(null)

  const load = useCallback(() => {
    fetch(`${apiBase}/api/briefing/history?limit=30`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: { items?: HistoryItem[] }) => {
        setItems(Array.isArray(d.items) ? d.items : [])
        setFailed(false)
      })
      .catch(() => setFailed(true))
  }, [apiBase])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (refreshKey) load() }, [refreshKey, load])

  const latestBySlot = SLOT_ORDER.map((slot) => {
    const idx = items?.findIndex((item) => item.slot === slot && item.success !== false) ?? -1
    return { slot, item: idx >= 0 ? items?.[idx] : undefined, idx: idx >= 0 ? idx : undefined }
  })

  const open = (item: HistoryItem, idx: number) => setModalState({ item, idx })

  return (
    <>
      <section className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">Latest Briefings</p>
            <h3 className="font-display text-xl font-black text-beige">장전·장중·마감 최신 브리핑</h3>
          </div>
          <button type="button" onClick={load} className="inline-flex items-center gap-2 rounded-chip border border-line bg-card-2 px-3 py-2 text-xs font-bold text-greige hover:border-hanwha hover:text-hanwha">
            <RefreshCw size={13} /> 새로고침
          </button>
        </div>

        {items === null && !failed ? (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40 rounded-card" />)}</div>
        ) : failed && items === null ? (
          <ErrorState title="생성이력 조회 실패" message="브리핑 생성이력을 불러오지 못했습니다." onRetry={load} />
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            {latestBySlot.map(({ slot, item, idx }) => <LatestCard key={slot} item={item} idx={idx} apiBase={apiBase} onOpen={open} />)}
          </div>
        )}

        <div className="rounded-card border border-line bg-card shadow-card">
          <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
            <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
              <History size={13} strokeWidth={2} /> 생성 이력
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] text-muted"><Clock3 size={12} /> 최신순</span>
          </header>
          <div className="max-h-[420px] overflow-y-auto p-3">
            {items && items.length === 0 && <EmptyState icon={<History size={18} strokeWidth={1.75} />} title="생성이력 없음" description="아직 생성된 브리핑이 없습니다." className="border-0 bg-transparent px-2 py-8" />}
            {items && items.length > 0 && <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">{items.map((it, i) => <li key={`${it.ts_epoch ?? it.ts ?? i}-${i}`}><HistoryRow item={it} idx={i} onOpen={open} /></li>)}</ul>}
          </div>
        </div>
      </section>
      {modalState && <HistoryModal item={modalState.item} idx={modalState.idx} apiBase={apiBase} onClose={() => setModalState(null)} />}
    </>
  )
}
