# 한화손보 "AI 운용본부 OS" — 디자인 시스템 가이드

테마: **Warm Dark Terminal**. 절제된 고급스러움. 색은 토큰으로만, 하드코딩 hex 금지.
모든 비동기 뷰는 (1) 로딩 스켈레톤, (2) 빈 상태, (3) 에러 상태 3종을 반드시 갖춘다.

---

## 1. 색 토큰 (tailwind.config.ts → theme.extend.colors)

한화 공식 브랜드 팔레트 계열만. 차가운 네이비 / 보라 그라데이션 / 제네릭 AI 룩 금지.

| 토큰 클래스 | HEX | 용도 |
|---|---|---|
| `bg-canvas` / `bg-bg` | `#241C19` | 메인 캔버스 배경 (둘은 alias) |
| `bg-card` | `#3A2F2C` | 카드/서피스 |
| `bg-card-2` | `#4A3D37` | 한 단계 밝은 서피스 / 호버 / 네스티드 |
| `border-line` / `border-border` | `#5A4A43` | 1px 웜브라운 보더 (둘은 alias) |
| `text-beige` | `#F7F1E9` | 본문 텍스트 |
| `text-muted` | `#A1948B` | 보조 / muted |
| `text-greige` | `#C9BBB0` | 밝은 보조 텍스트 |
| `text-hanwha` `bg-hanwha` `border-hanwha` | `#F37321` | 브랜드 1차 / CTA / 핵심 강조 (절제) |
| `*-hanwha-2` | `#F89B6C` | Orange2 |
| `*-hanwha-3` | `#FBB584` | Orange3 |
| `text-blue` `bg-blue` | `#3395BA` | Point Blue — 정보 / 링크 |
| `text-purple` `bg-purple` | `#A75788` | Point Purple — 특수 카테고리 |
| `text-up` `bg-up` `border-up` | `#E5484D` | **상승 / 이익 = 레드** (한국 관례) |
| `text-down` `bg-down` `border-down` | `#3395BA` | **하락 / 손실 = 블루** (한국 관례) |

> 등락색 규칙: 상승=빨강, 하락=파랑. **오렌지는 등락/신호색으로 절대 쓰지 않는다(브랜드 전용).**
> 기존 컴포넌트 호환: `bg-bg`(=canvas), `border-border`(=line) alias 유지 — 깨지 않는다.

### 폰트
| 토큰 | 폰트 | 용도 |
|---|---|---|
| `font-mono` | IBM Plex Mono | 숫자 / 티커 / 표 — `tabular-nums` 필수 |
| `font-sans` | Noto Sans KR | 한글 본문 (기본) |
| `font-display` | **Sora** | 영문 디스플레이 / 헤드라인 |

### 라운드 / 그림자
- `rounded-card`(18px) · `rounded-chip`(11px) · `rounded-pill`(999px)
- `shadow-card` · `shadow-card-hover` · `shadow-glow`(오렌지) · `shadow-inset`
- 애니메이션: `animate-shimmer`(스켈레톤), `animate-pulse-soft`(라이브 점)

---

## 2. 공유 프리미티브 (`src/components/ui/`)

import: `import { Card, Stat, ChangePill, ... } from '../components/ui'`

| 컴포넌트 | 주요 props | 비고 |
|---|---|---|
| `Card` | `title?` `eyebrow?` `action?` `noPadding?` `hover?` `className?` | 웜다크 서피스. 제목/액션 슬롯 |
| `Skeleton` / `SkeletonText` | `className` / `lines?` | shimmer 로딩 |
| `Stat` (=`Kpi`) | `label` `value` `delta?` `deltaPercent?` `hint?` | 라벨+큰수치+델타(up/down) |
| `ChangePill` | `value` `percent?` `digits?` `arrow?` `size?` | 등락 pill, 한국색+화살표 |
| `Badge` | `tone?`('neutral'\|'hanwha'\|'blue'\|'purple'\|'up'\|'down') `dot?` | 라벨 칩 |
| `Sparkline` | `data:number[]` `width?` `height?` `color?` `area?` `strokeWidth?` | 순수 SVG. 색 미지정시 방향 자동(up/down) |
| `SectionHeader` | `title` `eyebrow?` `description?` `action?` | 섹션 헤더 |
| `Spinner` | `size?` `className?` | 오렌지 스피너 |
| `EmptyState` | `title?` `description?` `icon?` `action?` | 빈 상태 |
| `ErrorState` | `title?` `message?` `onRetry?` `retryLabel?` | 에러 상태 + 재시도 |

---

## 3. 사용 규칙

1. **색은 토큰 클래스로만.** 인라인 hex / 임의값(`bg-[#...]`) 금지. SVG 내부에선 `var(--hanwha)` 등 CSS 변수 사용.
2. **수치/티커/표는 `font-mono tabular-nums`.** 정렬 흔들림 방지.
3. **오렌지는 절제.** 액티브 인디케이터 · CTA · 핵심 1개 수치만. 등락엔 절대 사용 금지.
4. **등락색은 ChangePill / Stat 의 delta 로.** 직접 색칠할 땐 상승 `text-up`, 하락 `text-down`.
5. **카드는 `Card` 프리미티브 사용.** 직접 만들면 `rounded-card border border-line bg-card shadow-card`.
6. **비동기 3종 필수:** 로딩=`Skeleton`/`Spinner`, 빈=`EmptyState`, 에러=`ErrorState`.
7. **모션은 과하지 않게.** 페이지 stagger(framer-motion), hover 마이크로(`hover` prop / `whileHover y:-2`).
8. **CSS 진입점은 `src/index.css` 단 하나.** `main.tsx` 가 import. (`src/style.css` 는 삭제됨)

---

_색: 토큰. 폰트: mono/sans/display. 상승=레드, 하락=블루. 오렌지=브랜드 전용._
