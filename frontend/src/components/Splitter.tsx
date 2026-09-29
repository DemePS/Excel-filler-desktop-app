// The handle between the side panel and the feed: drag it (or use the arrow keys) to resize the
// side panel; double-click to go back to the default width. The width is remembered.

import { useCallback, useEffect, useState } from 'react'

const KEY = 'excel-filler.sidebar-width'
export const DEFAULT_WIDTH = 320
const MIN = 220

const maxWidth = () => Math.max(MIN, Math.min(720, Math.round(window.innerWidth * 0.6)))
const clamp = (width: number) => Math.round(Math.min(maxWidth(), Math.max(MIN, width)))

function saved(): number {
  try {
    const value = Number(window.localStorage.getItem(KEY))
    return value ? clamp(value) : DEFAULT_WIDTH
  } catch {
    return DEFAULT_WIDTH
  }
}

function save(width: number) {
  try {
    window.localStorage.setItem(KEY, String(width))
  } catch {
    // not remembered; still resized
  }
}

export function useSidebarWidth() {
  const [width, setWidth] = useState(saved)
  const set = useCallback((next: number) => setWidth(clamp(next)), [])
  useEffect(() => save(width), [width])
  // A smaller window keeps the feed usable.
  useEffect(() => {
    const onResize = () => setWidth((w) => clamp(w))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return [width, set] as const
}

export function Splitter({ width, onResize }: { width: number; onResize: (width: number) => void }) {
  const [dragging, setDragging] = useState(false)

  const start = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    const startX = e.clientX
    const startWidth = width
    setDragging(true)
    const move = (ev: PointerEvent) => onResize(startWidth + ev.clientX - startX)
    const end = () => {
      setDragging(false)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', end)
      window.removeEventListener('pointercancel', end)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', end)
    window.addEventListener('pointercancel', end)
  }

  return (
    <div
      className={`splitter${dragging ? ' dragging' : ''}`}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the side panel"
      aria-valuenow={width}
      aria-valuemin={MIN}
      aria-valuemax={maxWidth()}
      tabIndex={0}
      title="Drag to resize; double-click to reset"
      onPointerDown={start}
      onDoubleClick={() => onResize(DEFAULT_WIDTH)}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') onResize(width - 20)
        else if (e.key === 'ArrowRight') onResize(width + 20)
        else return
        e.preventDefault()
      }}
    />
  )
}
