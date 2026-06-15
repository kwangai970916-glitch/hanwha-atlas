import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Activity, MoonStar, Play, Sunrise } from 'lucide-react'
import { Badge, ErrorState, Spinner, SectionHeader } from './ui'
import { cn } from '../lib/utils'
import {
  AdrCard,
  BriefingNewsCard,
  BriefingReport,
  GenerationStepper,
  HistoryRail,
  MoversCard,
  PngCard,
  RsQuadrantCard,
  type BriefingStatus,
  type RunStatus,
  type SlotId,
  containerVariants,
  formatElapsed,
  itemVariants,
  MAX_POLLS,
  POLL_INTERVAL_MS,
} from './briefing'

const SLOTS = [
  { id: 'premarket' as SlotId, label: '장전 브리핑', time: '07:00', desc: '간밤 글로벌 마감·매크로·뉴스를 장 시작 전 정리', Icon: Sunrise },
  { id: 'intraday' as SlotId, label: '장중 브리핑', time: '08:30', desc: '실시간 수급·섹터·종목 움직임을 장중 의사결정용으로 요약', Icon: Activity },
  { id: 'close' as SlotId, label: '마감 브리핑', time: '16:30', desc: '당일 시장 결산과 익일 체크포인트를 운용 코멘트로 압축', Icon: MoonStar },
] as const

export function BriefingAgent({ apiBase }: { apiBase: string }) {
  const [slot, setSlot] = useState<SlotId>('close')
  const [status, setStatus] = useState<RunStatus>('idle')
  const [result, setResult] = useState<BriefingStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [generatedAt, setGeneratedAt] = useState<number | null>(null)

  const runRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => () => stopTimer(), [stopTimer])

  // 슬롯 진입(마운트·전환) 시 백엔드 캐시에 남은 마지막 결과를 즉시 복원 —
  // 1~3분 재생성 없이 직전 리포트를 바로 보여준다. 활성 실행 중이면 runRef 가드로 무시.
  useEffect(() => {
    const runId = runRef.current
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${apiBase}/api/briefing/${slot}/status`)
        if (!res.ok) return
        const s = (await res.json()) as BriefingStatus
        if (cancelled || runRef.current !== runId) return
        if (s.success) {
          setResult(s)
          setStatus('done')
        }
      } catch {
        /* 캐시 복원 실패는 무시 — '지금 생성'으로 진행 가능 */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [apiBase, slot])

  const activeSlot = SLOTS.find((s) => s.id === slot)!
  const pngUrl = status === 'done' && result?.png_path ? `${apiBase}/api/briefing/${slot}/png?t=${result.png_path}` : null
  const pngUrls = status === 'done' && result?.png_paths?.length
    ? result.png_paths.map((p) => `${apiBase}/api/briefing/${slot}/png?t=${encodeURIComponent(p)}`)
    : null

  const generate = useCallback(async () => {
    const runId = ++runRef.current
    setStatus('running')
    setResult(null)
    setError(null)
    setElapsed(0)
    setGeneratedAt(null)

    stopTimer()
    const startedAt = Date.now()
    timerRef.current = setInterval(() => {
      if (runRef.current !== runId) return
      setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 1000)

    try {
      const trigger = await fetch(`${apiBase}/api/briefing/${slot}`, { method: 'POST' })
      if (!trigger.ok) throw new Error(`생성 요청 실패 (HTTP ${trigger.status})`)

      for (let i = 0; i < MAX_POLLS; i++) {
        if (i > 0) await new Promise<void>((r) => setTimeout(r, POLL_INTERVAL_MS))
        if (runRef.current !== runId) return
        try {
          const res = await fetch(`${apiBase}/api/briefing/${slot}/status`)
          if (!res.ok) throw new Error(`상태 조회 실패 (HTTP ${res.status})`)
          const s = (await res.json()) as BriefingStatus
          if (runRef.current !== runId) return
          if (s.success) {
            setResult(s)
            setGeneratedAt(Date.now())
            setStatus('done')
            stopTimer()
            return
          }
          if (s.success === false || s.error) {
            throw Object.assign(new Error(s.error || '리포트 생성에 실패했습니다.'), { fatal: true })
          }
        } catch (e) {
          // 백엔드가 실패를 보고하면 즉시 중단해 에러를 표시 — 일시적 네트워크 오류만 재시도
          if ((e as { fatal?: boolean }).fatal || i === MAX_POLLS - 1) throw e
        }
      }
      throw new Error('생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.')
    } catch (e) {
      if (runRef.current !== runId) return
      setError(e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.')
      setStatus('error')
      stopTimer()
    }
  }, [apiBase, slot, stopTimer])

  const selectSlot = (id: SlotId) => {
    if (id === slot) return
    runRef.current++
    stopTimer()
    setSlot(id)
    setStatus('idle')
    setResult(null)
    setError(null)
    setElapsed(0)
    setGeneratedAt(null)
  }

  const isRunning = status === 'running'
  const report = result?.report
  const interactive = result?.interactive

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={itemVariants}>
        <SectionHeader
          eyebrow="Briefing Agent"
          title="시황 브리핑 에이전트"
          description="장전·장중·마감 타이밍별로 시장 데이터, 섹터 흐름, 주요 뉴스와 운용 코멘트를 자동 생성합니다."
          action={<Badge tone={isRunning ? 'hanwha' : status === 'done' ? 'blue' : 'neutral'} dot>{isRunning ? '생성 중' : status === 'done' ? '완료' : '대기'}</Badge>}
        />
      </motion.div>

      <motion.div variants={itemVariants}>
        <HistoryRail apiBase={apiBase} refreshKey={status === 'done' ? result?.png_path : null} />
      </motion.div>

      <div className="space-y-6">
        <motion.div variants={itemVariants} className="grid gap-3 sm:grid-cols-3">
          {SLOTS.map((s) => {
            const selected = s.id === slot
            const ActiveIcon = s.Icon
            return (
              <motion.button
                key={s.id}
                type="button"
                onClick={() => selectSlot(s.id)}
                whileHover={{ y: -2 }}
                transition={{ type: 'spring', stiffness: 280, damping: 26 }}
                aria-pressed={selected}
                className={cn(
                  'group relative overflow-hidden rounded-[22px] border p-4 text-left shadow-card transition-colors',
                  selected ? 'border-hanwha/65 bg-[#2b1d16] shadow-glow' : 'border-line/80 bg-card/85 hover:border-greige/35 hover:bg-card-2/80',
                )}
              >
                {selected && <motion.span layoutId="briefing-slot-indicator" className="absolute inset-y-0 left-0 w-1.5 bg-hanwha" />}
                <div className="flex items-start justify-between gap-2">
                  <div className={cn('relative grid h-10 w-10 place-items-center rounded-[14px] border', selected ? 'border-hanwha/30 bg-hanwha/15 text-hanwha' : 'border-line bg-canvas/35 text-muted group-hover:text-greige')}>
                    <ActiveIcon size={18} strokeWidth={1.9} />
                  </div>
                  <span className="font-mono text-xs font-extrabold tabular-nums text-greige">{s.time}</span>
                </div>
                <p className={cn('mt-3 font-display text-[15px] font-black tracking-tight', selected ? 'text-beige' : 'text-greige')}>{s.label}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted">{s.desc}</p>
              </motion.button>
            )
          })}
        </motion.div>

        <motion.div variants={itemVariants} className="flex flex-col gap-3 rounded-card border border-line bg-card/80 p-4 shadow-card sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted">
            선택된 브리핑 <span className="font-display font-bold text-beige">{activeSlot.label}</span>
            <span className="ml-2 font-mono text-xs tabular-nums text-greige">{activeSlot.time}</span>
          </p>
          <motion.button
            type="button"
            onClick={generate}
            disabled={isRunning}
            whileHover={isRunning ? undefined : { y: -1 }}
            whileTap={isRunning ? undefined : { scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 320, damping: 24 }}
            className={cn('inline-flex items-center justify-center gap-2 rounded-[14px] border px-5 py-2.5 text-sm font-extrabold tracking-tight transition-colors', isRunning ? 'cursor-not-allowed border-line bg-card-2 text-muted' : 'border-hanwha/60 bg-hanwha text-canvas shadow-glow hover:bg-hanwha-2')}
          >
            {isRunning ? <><Spinner size={16} className="text-current" /><span className="font-mono tabular-nums">{formatElapsed(elapsed)}</span>생성 중</> : <><Play size={16} strokeWidth={2.2} />{status === 'done' || status === 'error' ? '다시 생성' : '지금 생성'}</>}
          </motion.button>
        </motion.div>

        <AnimatePresence>
          {isRunning && (
            <motion.div key="stepper" variants={itemVariants} initial="hidden" animate="show" exit={{ opacity: 0, y: -6, transition: { duration: 0.15 } }}>
              <div className="rounded-card border border-line bg-card shadow-card">
                <header className="border-b border-line px-5 pb-3 pt-4">
                  <div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-hanwha">{activeSlot.label}</div>
                  <h3 className="font-display text-base font-bold tracking-tight text-beige">시황 리포트 생성 중</h3>
                </header>
                <div className="px-5 pb-5 pt-4"><GenerationStepper elapsed={elapsed} slotLabel={activeSlot.label} /></div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {status === 'error' && !isRunning && <motion.div variants={itemVariants}><ErrorState title="리포트 생성 실패" message={error ?? '리포트를 생성하지 못했습니다.'} onRetry={generate} retryLabel="다시 생성" /></motion.div>}
        {status === 'done' && result && (
          <motion.div variants={itemVariants} className="space-y-6">
            {report && <BriefingReport report={report} generatedAt={generatedAt} />}
            <RsQuadrantCard interactive={interactive} />
            <AdrCard interactive={interactive} />
            <MoversCard interactive={interactive} />
            <BriefingNewsCard interactive={interactive} />
            <PngCard pngUrl={pngUrl} pngUrls={pngUrls} slot={slot} label={activeSlot.label} onRefresh={generate} />
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}

export default BriefingAgent

