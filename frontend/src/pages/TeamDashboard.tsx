import { useEffect, useMemo, useState } from 'react'
import { getTeamDashboard, type TeamDashboardResponse } from '../api'
import { KpiCard } from '../components/KpiCard'
import { TopAppsChart } from '../components/TopAppsChart'
import AppUsagePie from '../components/AppUsagePie'

type SortKey = 'productive' | 'neutral' | 'distracting' | 'idle' | 'total'

function minutes(pb: any, key: SortKey): number {
  if (key === 'total') return Number(pb?.total_minutes ?? 0)
  return Number(pb?.productivity_breakdown?.[key] ?? 0)
}

function metricLabel(k: SortKey): string {
  if (k === 'total') return 'Total'
  return k.charAt(0).toUpperCase() + k.slice(1)
}

function metricColor(k: SortKey): string {
  if (k === 'productive') return '#10b981'
  if (k === 'neutral') return '#3b82f6'
  if (k === 'distracting') return '#ef4444'
  if (k === 'idle') return '#6b7280'
  return 'var(--accent)'
}

function formatDurationSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0s'
  const s = Math.floor(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${ss}s`
  return `${ss}s`
}

function minutesToText(min: number): string {
  const m = Math.max(0, Math.floor(min))
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h}h ${r}m` : `${h}h`
}

function currentStatusText(m: TeamDashboardResponse['members'][number]): string {
  if (!m.current_app_name) return 'No recent activity'
  const title = m.current_window_title ? ` · ${m.current_window_title}` : ''
  let dur = ''
  if (m.current_started_at && m.current_ended_at) {
    const started = new Date(m.current_started_at).getTime()
    const ended = new Date(m.current_ended_at).getTime()
    const seconds = Math.max(0, Math.floor((ended - started) / 1000))
    dur = ` · ${formatDurationSeconds(seconds)}`
  }
  return `${m.current_app_name}${title}${dur}`
}

function currentDuration(m: TeamDashboardResponse['members'][number]): string | null {
  if (!m.current_started_at) return null
  const started = new Date(m.current_started_at).getTime()
  const ended = m.current_ended_at ? new Date(m.current_ended_at).getTime() : Date.now()
  const seconds = Math.max(0, Math.floor((ended - started) / 1000))
  return formatDurationSeconds(seconds)
}

interface Props {
  teamId: number
  teamName: string
  day: string
  onDayChange: (day: string) => void
  onLoadToday: () => void
  onBack: () => void
  onSelectUser: (machineGuid: string) => void
}

export default function TeamDashboard({
  teamId,
  teamName,
  day,
  onDayChange,
  onLoadToday,
  onBack,
  onSelectUser,
}: Props) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<TeamDashboardResponse | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('productive')

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        setLoading(true)
        const d = await getTeamDashboard(teamId, day)
        if (!cancelled) setData(d)
      } catch (e) {
        console.error(e)
        if (!cancelled) setData(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [teamId, day])

  const sortedMembers = useMemo(() => {
    if (!data) return []
    const copy = [...data.members]
    copy.sort((a, b) => minutes(b as any, sortKey) - minutes(a as any, sortKey))
    return copy
  }, [data, sortKey])

  return (
    <div className="page-shell">
      <div className="page-header">
        <div className="page-header-left">
          <div className="eyebrow">Team Tracking Dashboard</div>
          <h1>{teamName}</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            Aggregated metrics and member performance for this team.
          </p>
        </div>
        <div className="page-header-right">
          <button className="btn btn-ghost" onClick={onBack} style={{ marginRight: 8 }}>← Back</button>
          <div>
            <div className="date-label">Date</div>
            <input type="date" value={day} onChange={e => onDayChange(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={onLoadToday}>Today</button>
        </div>
      </div>

      {loading && (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading team dashboard…
        </div>
      )}

      {!loading && data && (
        <>
          {/* KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12, marginBottom: 18 }}>
            {data.aggregate.kpis.map((k, i) => <KpiCard key={i} item={k} />)}
          </div>

          {/* Top Applications: bar + pie */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
            <TopAppsChart items={data.aggregate.top_apps} />
            <div className="card chart-card">
              <h3>App usage</h3>
              <div className="chart-wrap" style={{ height: 300 }}>
                <AppUsagePie items={data.aggregate.timeline} />
              </div>
            </div>
          </div>

          {/* Sort + member cards */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
              <div>
                <h2 style={{ fontSize: 18, marginBottom: 4 }}>Members</h2>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Sort by: {sortKey.toUpperCase()}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {(['productive', 'neutral', 'total', 'distracting', 'idle'] as SortKey[]).map(k => (
                  <button
                    key={k}
                    className={`btn ${sortKey === k ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '6px 12px', fontSize: 12 }}
                    onClick={() => setSortKey(k)}
                  >
                    {k === 'total' ? 'Total' : k.charAt(0).toUpperCase() + k.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
            {sortedMembers.map(m => {
              const pb = m.productivity_breakdown
              const focusMinutes = sortKey === 'total' ? (m.total_minutes ?? 0) : (pb as any)[sortKey] ?? 0
              const focusLabel = metricLabel(sortKey)
              const focusColor = metricColor(sortKey)
              const statusDuration = currentDuration(m)
              return (
                <div
                  key={m.user_id}
                  className="card"
                  style={{
                    padding: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                    border: `1px solid var(--border)`,
                    boxShadow: 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <div>
                      <div style={{ fontWeight: 700 }}>{m.full_name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{m.email}</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                      <div
                        className="badge"
                        style={{
                          background: 'var(--bg-elevated)',
                          color: 'var(--text-muted)',
                          border: `1px solid ${focusColor}33`,
                        }}
                        title={`Sorted by ${focusLabel}`}
                      >
                        {focusLabel}: <strong style={{ color: 'var(--text-primary)' }}>{minutesToText(focusMinutes)}</strong>
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        Total: <strong style={{ color: 'var(--text-secondary)' }}>{minutesToText(m.total_minutes ?? 0)}</strong>
                      </div>
                    </div>
                  </div>

                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    <div><span style={{ color: 'var(--text-muted)' }}>Productive</span> · <strong>{pb.productive ?? 0}m</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>Neutral</span> · <strong>{pb.neutral ?? 0}m</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>Distracting</span> · <strong>{pb.distracting ?? 0}m</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>Idle</span> · <strong>{pb.idle ?? 0}m</strong></div>
                  </div>

                  <div style={{ marginTop: 4, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Current status</div>
                      {statusDuration && (
                        <div className="badge" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                          {statusDuration}
                        </div>
                      )}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 6 }}>
                      <strong style={{ color: 'var(--text-primary)' }}>{m.current_app_name ?? '—'}</strong>
                      {m.current_window_title ? (
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                          {m.current_window_title}
                        </div>
                      ) : (
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                          {currentStatusText(m)}
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ marginTop: 'auto', paddingTop: 12 }}>
                    {m.machine_guid ? (
                      <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={() => onSelectUser(m.machine_guid!)}>
                        View full dashboard
                      </button>
                    ) : (
                      <div style={{ textAlign: 'center', padding: 10, color: 'var(--text-muted)', background: 'var(--bg-elevated)', borderRadius: 8, fontSize: 12 }}>
                        No device linked
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

