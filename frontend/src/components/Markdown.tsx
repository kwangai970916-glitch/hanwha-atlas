// src/components/Markdown.tsx
// 공용 Markdown 렌더러 — 웜다크 prose, 브랜드 토큰 색만 사용(prose-invert 의존 제거).
// IdeaLab / AICommittee 가 동일 출력을 내도록 단일 컴포넌트로 일원화.
import ReactMarkdown from 'react-markdown'

export function Markdown({ children }: { children: string }) {
  return (
    <div
      className="space-y-2 text-sm leading-relaxed text-greige
                 [&_a]:text-blue [&_a]:underline
                 [&_code]:rounded [&_code]:bg-canvas [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[12px] [&_code]:text-hanwha-3
                 [&_h1]:text-hanwha [&_h2]:text-hanwha [&_h3]:text-hanwha [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold
                 [&_li]:ml-1
                 [&_p]:text-greige
                 [&_strong]:font-semibold [&_strong]:text-beige
                 [&_table]:text-xs [&_th]:text-muted [&_td]:border [&_td]:border-line
                 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5"
    >
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}
