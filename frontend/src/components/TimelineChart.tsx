import type { TimelineItem } from '../types'

const labelColor: Record<TimelineItem['productivity_label'], string> = {
  productive: 'pill productive',
  neutral: 'pill neutral',
  distracting: 'pill distracting',
}

function fmt(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

type Props = {
  items: TimelineItem[]
}

export function TimelineChart({ items }: Props) {
  return (
    <div className="card">
      <h3>Timeline</h3>
      <div className="timeline-list">
        {items.length === 0 && <div className="muted">No events for this day.</div>}
        {items.map((item, idx) => (
          <div className="timeline-row" key={`${item.started_at}-${idx}`}>
            <div className="timeline-time">
              {fmt(item.started_at)} - {fmt(item.ended_at)}
            </div>
            <div>
              <div className="timeline-app">{item.app_name}</div>
              <div className="muted">{item.window_title || 'Untitled activity'}</div>
            </div>
            <div className={labelColor[item.productivity_label]}>{item.productivity_label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
