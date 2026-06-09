import { motion } from 'framer-motion'
import { CheckCircle2, Cpu, Database, LayoutGrid } from 'lucide-react'
import { formatElapsed } from './utils'

type Step = {
  id: number
  label: string
  sublabel: string
  icon: typeof Database
  startsAt: number
  endsAt: number
  image: string
}

const STEPS: Step[] = [
  {
    id: 0,
    label: '시장 데이터 수집',
    sublabel: '지수·ADR·섹터·종목·뉴스 데이터를 수집합니다',
    icon: Database,
    startsAt: 0,
    endsAt: 4,
    image: '/illustrations/process/briefing-data.png',
  },
  {
    id: 1,
    label: 'AI 시황 작성',
    sublabel: '시장 흐름을 해석해 브리핑 문장과 운용 코멘트를 작성합니다',
    icon: Cpu,
    startsAt: 4,
    endsAt: 18,
    image: '/illustrations/process/briefing-ai.png',
  },
  {
    id: 2,
    label: '리포트 렌더링',
    sublabel: '차트와 리포트 이미지를 패키징합니다',
    icon: LayoutGrid,
    startsAt: 18,
    endsAt: Infinity,
    image: '/illustrations/process/briefing-render.png',
  },
]

function currentStep(elapsed: number): number {
  for (let i = STEPS.length - 1; i >= 0; i--) {
    if (elapsed >= STEPS[i].startsAt) return i
  }
  return 0
}

export function GenerationStepper({ elapsed, slotLabel }: { elapsed: number; slotLabel: string }) {
  const active = currentStep(elapsed)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 rounded-chip border border-line bg-card-2/60 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-beige">{slotLabel} 리포트를 생성하고 있습니다</p>
          <p className="mt-0.5 text-xs text-muted">
            경과 <span className="font-mono tabular-nums text-greige">{formatElapsed(elapsed)}</span>
          </p>
        </div>
        <span className="inline-flex items-center gap-2 font-mono text-xs font-bold tabular-nums text-hanwha">
          <motion.span
            className="h-1.5 w-1.5 rounded-full bg-hanwha"
            animate={{ opacity: [0.35, 1, 0.35], scale: [0.9, 1.25, 0.9] }}
            transition={{ repeat: Infinity, duration: 0.9, ease: 'easeInOut' }}
          />
          {STEPS[active].label}
        </span>
      </div>

      <ol className="grid gap-3 md:grid-cols-3">
        {STEPS.map((step, idx) => {
          const StepIcon = step.icon
          const isDone = active > idx
          const isActive = active === idx
          const isPending = active < idx

          return (
            <motion.li
              key={step.id}
              animate={isActive ? { y: [0, -3, 0] } : { y: 0 }}
              transition={isActive ? { repeat: Infinity, duration: 1.25, ease: 'easeInOut' } : {}}
              className={[
                'relative overflow-hidden rounded-card border p-4 transition-colors',
                isDone
                  ? 'border-hanwha/35 bg-hanwha/[0.055]'
                  : isActive
                    ? 'border-hanwha/65 bg-card-2/60 shadow-glow'
                    : 'border-line bg-canvas/35',
              ].join(' ')}
            >
              {idx < STEPS.length - 1 && (
                <span className={['pointer-events-none absolute left-[calc(100%-10px)] top-[76px] z-20 hidden h-0.5 w-8 md:block', isDone ? 'bg-hanwha/70' : 'bg-line'].join(' ')} />
              )}

              <div className="mb-3 flex items-center justify-between gap-2">
                <div
                  className={[
                    'grid h-8 w-8 place-items-center rounded-full border transition-colors',
                    isDone
                      ? 'border-hanwha bg-hanwha/20 text-hanwha'
                      : isActive
                        ? 'border-hanwha bg-hanwha/10 text-hanwha'
                        : 'border-line bg-card-2/40 text-muted',
                  ].join(' ')}
                >
                  {isDone ? <CheckCircle2 size={15} strokeWidth={2.2} /> : <StepIcon size={14} />}
                </div>
                <span className="font-mono text-[11px] font-semibold tabular-nums text-muted">{String(idx + 1).padStart(2, '0')}/03</span>
              </div>

              <div className="relative mb-3 grid h-36 place-items-center overflow-hidden rounded-card bg-card/30 pb-2 pt-1">
                {isActive && (
                  <motion.span
                    className="absolute inset-x-6 bottom-2 h-px rounded-full bg-hanwha/80"
                    animate={{ scaleX: [0.15, 1, 0.15], opacity: [0.35, 1, 0.35] }}
                    transition={{ repeat: Infinity, duration: 0.95, ease: 'easeInOut' }}
                  />
                )}
                <motion.img
                  src={step.image}
                  alt=""
                  aria-hidden="true"
                  loading="lazy"
                  decoding="async"
                  className={['h-full w-full object-contain transition-opacity', isPending ? 'opacity-35 grayscale' : 'opacity-100'].join(' ')}
                  animate={isActive ? { scale: [1, 1.045, 1] } : { scale: 1 }}
                  transition={isActive ? { repeat: Infinity, duration: 1.35, ease: 'easeInOut' } : {}}
                />
              </div>

              <div className="min-w-0">
                <p className={['text-sm font-semibold', isDone ? 'text-greige' : isActive ? 'text-beige' : 'text-muted'].join(' ')}>
                  {step.label}
                  {isActive && (
                    <motion.span
                      animate={{ opacity: [1, 0.3, 1] }}
                      transition={{ repeat: Infinity, duration: 0.8, ease: 'easeInOut' }}
                      className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-hanwha align-middle"
                    />
                  )}
                </p>
                <p className="mt-0.5 text-xs text-muted">{isDone ? '완료' : isPending ? '대기 중' : step.sublabel}</p>
              </div>
            </motion.li>
          )
        })}
      </ol>
    </div>
  )
}
