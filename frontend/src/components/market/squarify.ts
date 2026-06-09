/**
 * squarify — Bruls et al. 의 squarified treemap 레이아웃.
 * 주어진 사각형(rect) 안에 value 비례 면적으로 셀을 배치하되,
 * 각 셀의 종횡비를 1에 가깝게 유지한다(finviz 스타일 히트맵용).
 */
export type Rect = { x: number; y: number; w: number; h: number }
export interface SqItem<T> { value: number; data: T }
export interface SqResult<T> { rect: Rect; data: T }

export function squarify<T>(items: SqItem<T>[], rect: Rect): SqResult<T>[] {
  const out: SqResult<T>[] = []
  const clean = items.filter((i) => i.value > 0)
  const total = clean.reduce((s, i) => s + i.value, 0)
  if (total <= 0 || rect.w <= 0 || rect.h <= 0) return out

  const area = rect.w * rect.h
  const scaled = clean.map((i) => ({ v: (i.value / total) * area, data: i.data }))

  let free: Rect = { ...rect }
  let row: { v: number; data: T }[] = []

  const shortest = () => Math.min(free.w, free.h)

  const worst = (r: { v: number }[], side: number): number => {
    if (r.length === 0) return Infinity
    const sum = r.reduce((s, x) => s + x.v, 0)
    const max = Math.max(...r.map((x) => x.v))
    const min = Math.min(...r.map((x) => x.v))
    const side2 = side * side
    const sum2 = sum * sum
    return Math.max((side2 * max) / sum2, sum2 / (side2 * min))
  }

  const layoutRow = (r: { v: number; data: T }[]) => {
    const sum = r.reduce((s, x) => s + x.v, 0)
    if (sum <= 0) return
    if (free.w >= free.h) {
      const colW = sum / free.h
      let y = free.y
      for (const it of r) {
        const h = (it.v / sum) * free.h
        out.push({ rect: { x: free.x, y, w: colW, h }, data: it.data })
        y += h
      }
      free = { x: free.x + colW, y: free.y, w: free.w - colW, h: free.h }
    } else {
      const rowH = sum / free.w
      let x = free.x
      for (const it of r) {
        const w = (it.v / sum) * free.w
        out.push({ rect: { x, y: free.y, w, h: rowH }, data: it.data })
        x += w
      }
      free = { x: free.x, y: free.y + rowH, w: free.w, h: free.h - rowH }
    }
  }

  for (const item of scaled) {
    const side = shortest()
    const next = [...row, item]
    if (row.length === 0 || worst(next, side) <= worst(row, side)) {
      row = next
    } else {
      layoutRow(row)
      row = [item]
    }
  }
  if (row.length) layoutRow(row)
  return out
}
