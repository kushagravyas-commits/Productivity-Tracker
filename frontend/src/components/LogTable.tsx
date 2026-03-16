import type { TimelineItem } from '../types'

interface Props {
  items: TimelineItem[]
  sortBy: string
  sortOrder: string
  onSort: (by: string, order: string) => void
}

const CAT_COLOR: Record<string, string> = {
  productive:  '#10b981',
  neutral:     '#3b82f6',
  distracting: '#ef4444',
  idle:        '#6b7280',
}

function fmtTime(iso: string) {
  return iso.slice(11, 16)
}

function fmtDur(startIso: string, endIso: string) {
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime()
  if (ms < 60000) return `${Math.round(ms / 1000)}s`
  if (ms < 3600000) return `${Math.round(ms / 60000)}m`
  return `${(ms / 3600000).toFixed(1)}h`
}

export default function LogTable({ items, sortBy, sortOrder, onSort }: Props) {
  const cols = [
    { key: 'time',     label: 'Time' },
    { key: 'duration', label: 'Duration' },
    { key: 'app',      label: 'App' },
    { key: '',         label: 'Window Title' },
    { key: '',         label: 'Category' },
  ]

  function handleSort(key: string) {
    if (!key) return
    if (sortBy === key) onSort(key, sortOrder === 'asc' ? 'desc' : 'asc')
    else onSort(key, 'asc')
  }

  const arrow = (key: string) => sortBy === key ? (sortOrder === 'asc' ? ' ↑' : ' ↓') : ''

  return (
    <div className="log-table-wrap">
      <table className="log-table">
        <thead>
          <tr>
            {cols.map(c => (
              <th
                key={c.label}
                className={c.key && sortBy === c.key ? 'sorted' : ''}
                onClick={() => handleSort(c.key)}
              >
                {c.label}
                {c.key && <span className="sort-arrow">{arrow(c.key)}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={i}>
              <td className="td-time">{fmtTime(item.started_at)} – {fmtTime(item.ended_at)}</td>
              <td className="td-dur">{fmtDur(item.started_at, item.ended_at)}</td>
              <td className="td-app">
                <span className="log-color-dot" style={{ background: CAT_COLOR[item.productivity_label] ?? '#6b7280' }} />
                {item.app_name}
              </td>
              <td className="td-title">{item.window_title || '—'}</td>
              <td>
                <span className={`badge badge-${item.productivity_label}`}>
                  {item.productivity_label}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
