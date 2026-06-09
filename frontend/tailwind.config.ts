import type { Config } from 'tailwindcss'

/**
 * 한화손보 "AI 운용본부 OS" — Warm Dark Terminal 디자인 토큰
 * 모든 색은 한화 공식 브랜드 팔레트 계열만 사용한다.
 * 차가운 네이비/제네릭 AI 그라데이션 금지.
 *
 * 등락색(한국 관례): 상승/이익 = up(레드 #E5484D), 하락/손실 = down(블루 #3395BA)
 * 오렌지(hanwha)는 브랜드 전용 신호색 — 등락 표시에 쓰지 말 것.
 *
 * 기존 컴포넌트가 쓰는 alias(bg-bg, border-border 등)도 함께 정의해 호환성 유지.
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // --- 캔버스 / 서피스 (딥 다크 브라운 계열) ---
        canvas: '#241C19',          // 메인 배경
        bg: '#241C19',              // alias (기존 bg-bg 호환)
        card: '#3A2F2C',            // 카드/서피스 (캔버스보다 밝은 웜브라운)
        'card-2': '#4A3D37',        // 한 단계 더 밝은 서피스 (호버/네스티드)
        line: '#5A4A43',            // 1px 웜브라운 보더 (낮은 대비)
        border: '#5A4A43',          // alias (기존 border-border 호환)

        // --- 텍스트 ---
        beige: '#F7F1E9',           // 본문 (Light Beige)
        muted: '#A1948B',           // 보조/muted (Warm Brown ~ Greige)
        greige: '#C9BBB0',          // 더 밝은 보조 텍스트

        // --- 한화 브랜드 액센트 (절제된 포인트) ---
        hanwha: '#F37321',          // 브랜드 1차 / CTA / 핵심 강조
        'hanwha-2': '#F89B6C',      // Orange2
        'hanwha-3': '#FBB584',      // Orange3

        // --- 데이터 보조 강조 ---
        blue: '#3395BA',            // Point Blue (정보/링크)
        purple: '#A75788',          // Point Purple (특수 카테고리)

        // --- 등락색 (한국 관례) ---
        up: '#E5484D',              // 상승/이익 = 레드
        down: '#3395BA',            // 하락/손실 = 블루
      },
      fontFamily: {
        mono: ['\"Pretendard\"', '\"Noto Sans KR\"', '\"Malgun Gothic\"', '\"Apple SD Gothic Neo\"', 'system-ui', 'sans-serif'],
        sans: ['\"Pretendard\"', '\"Noto Sans KR\"', '\"Malgun Gothic\"', '\"Apple SD Gothic Neo\"', 'system-ui', 'sans-serif'],
        display: ['\"Pretendard\"', '\"Noto Sans KR\"', '\"Malgun Gothic\"', '\"Apple SD Gothic Neo\"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        card: '18px',     // 카드 16~20px
        chip: '11px',     // 칩/버튼 10~12px
        pill: '999px',
      },
      boxShadow: {
        card: '0 12px 32px rgba(0,0,0,0.32)',
        'card-hover': '0 18px 44px rgba(0,0,0,0.40)',
        glow: '0 0 0 1px rgba(243,115,33,0.30), 0 10px 30px rgba(243,115,33,0.18)',
        inset: 'inset 0 1px 0 rgba(247,241,233,0.04)',
      },
      backgroundImage: {
        'warm-radial':
          'radial-gradient(circle at 12% -8%, rgba(243,115,33,0.10), transparent 38%), radial-gradient(circle at 92% 4%, rgba(167,87,136,0.07), transparent 34%)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

export default config
