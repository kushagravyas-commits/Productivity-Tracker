import { useMemo } from 'react'
import type { TimelineItem } from '../types'

interface Props { items: TimelineItem[] }

const CAT_COLORS: Record<string, string> = {
  productive:  '#10b981',
  neutral:     '#3b82f6',
  distracting: '#ef4444',
  idle:        '#6b7280',
}

export default function ActivityTimeline({ items }: Props) {
  const { blocks, startHour, endHour, spanHours } = useMemo(() => {
    if (!items.length) return { blocks: [], startHour: 8, endHour: 18, spanHours: 10 }
    const starts = items.map(i => new Date(i.started_at).getHours())
    const ends   = items.map(i => new Date(i.ended_at).getHours())
    const startHour = Math.max(0, Math.min(...starts) - 0)
    // Keep one full trailing hour so late events (e.g. 23:43) are visible.
    const endHour   = Math.min(24, Math.max(...ends) + 1)
    const spanHours = Math.max(1, endHour - startHour)
    const rangeMs = spanHours * 3600000
    const baseMs = new Date(items[0].started_at).setHours(startHour, 0, 0, 0)

    const blocks = items.map(item => {
      const s = new Date(item.started_at).getTime()
      const e = new Date(item.ended_at).getTime()
      const left = Math.max(0, ((s - baseMs) / rangeMs) * 100)
      const width = Math.max(0.15, ((e - s) / rangeMs) * 100)
      return { ...item, left, width }
    })

    return { blocks, startHour, endHour, spanHours }
  }, [items])

  if (!items.length) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
      No activity data for this view
    </div>
  )

  const hours = Array.from({ length: endHour - startHour + 1 }, (_, i) => startHour + i)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0' }}>
      {/* Hour Labels */}
      <div style={{ position: 'relative', height: 20, marginLeft: 0, marginRight: 0 }}>
        {hours.map(h => (
          <div key={h} style={{
            position: 'absolute',
            left: `${((h - startHour) / spanHours) * 100}%`,
            transform: 'translateX(-50%)',
            fontSize: 10,
            color: 'var(--text-muted)',
            fontVariantNumeric: 'tabular-nums',
          }}>
            {String(h).padStart(2, '0')}:00
          </div>
        ))}
      </div>

      {/* Timeline Track */}
      <div style={{ flex: 1, position: 'relative', background: 'var(--bg-elevated)', borderRadius: 8, overflow: 'hidden', minHeight: 48 }}>
        {/* Hour grid lines */}
        {hours.map(h => (
          <div key={h} style={{
            position: 'absolute',
            top: 0, bottom: 0,
            left: `${((h - startHour) / spanHours) * 100}%`,
            width: 1,
            background: 'var(--border)',
          }} />
        ))}

        {/* Activity Blocks */}
        {blocks.map((b, i) => (
          <div
            key={i}
            title={`${b.app_name} — ${b.window_title || ''}\n${b.started_at.slice(11, 16)} → ${b.ended_at.slice(11, 16)}`}
            style={{
              position: 'absolute',
              top: 6,
              bottom: 6,
              left: `${b.left}%`,
              width: `${b.width}%`,
              background: CAT_COLORS[b.productivity_label] || 'var(--accent)',
              borderRadius: 4,
              opacity: 0.85,
              cursor: 'default',
              minWidth: 2,
              transition: 'opacity 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
            onMouseLeave={e => (e.currentTarget.style.opacity = '0.85')}
          />
        ))}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, justifyContent: 'flex-end' }}>
        {Object.entries(CAT_COLORS).map(([cat, color]) => (
          <div key={cat} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </div>
        ))}
      </div>
    </div>
  )
}
