import type { SessionItem } from '../types'

function fmt(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

type Props = {
  sessions: SessionItem[]
}

export function EventTable({ sessions }: Props) {
  return (
    <div className="card">
      <h3>Sessions</h3>
      <div className="session-list">
        {sessions.length === 0 && <div className="muted">No session history available.</div>}
        {sessions.map((session, idx) => (
          <div className="session-item" key={`${session.started_at}-${idx}`}>
            <div className="session-heading">
              <strong>
                {fmt(session.started_at)} - {fmt(session.ended_at)}
              </strong>
              <span>{Math.round(session.duration_seconds / 60)} min</span>
            </div>
            <p>{session.summary}</p>
            <div className="chips">
              {session.top_apps.map((app) => (
                <span key={`${session.started_at}-${app.app_name}`} className="chip">
                  {app.app_name}: {app.display}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
