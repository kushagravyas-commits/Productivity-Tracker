import { useMemo } from 'react'
import type { DashboardResponse, HistoryResponse } from '../types'
import type { WeeklyBreakdown } from '../App'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const LIVE_REFRESH_MS = 5000

function todayString() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function formatMinutes(min: number) {
  if (min < 60) return `${min}m`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

interface DashboardPageProps {
  day: string
  dashboard: DashboardResponse | null
  history: HistoryResponse | null
  loading: boolean
  message: string
  lastUpdated: string
  weeklyBreakdowns: WeeklyBreakdown[]
  onDayChange: (day: string) => void
  onLoadToday: () => void
}

export default function Dashboard({
  day,
  dashboard,
  loading,
  message,
  lastUpdated,
  weeklyBreakdowns,
  onDayChange,
  onLoadToday,
}: DashboardPageProps) {
  const isToday = day === todayString()

  const metrics = useMemo(() => {
    if (!dashboard) return { productivity: 0, totalMinutes: 0, productive: 0, neutral: 0, distracting: 0, idle: 0, topApps: [], switches: 0 }
    const { productive = 0, neutral = 0, distracting = 0, idle = 0 } = dashboard.productivity_breakdown
    const total = productive + neutral + distracting + idle
    const productivity = total > 0 ? Math.round((productive / total) * 100) : 0
    return {
      productivity,
      totalMinutes: total,
      productive,
      neutral,
      distracting,
      idle,
      topApps: dashboard.top_apps,
      switches: dashboard.timeline?.length ?? 0,
    }
  }, [dashboard])

  // Weekly chart data — built from 7 real API responses (day-6 through selected day)
  const weeklyData = useMemo(() => {
    const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    if (weeklyBreakdowns.length === 7) {
      return weeklyBreakdowns.map(wb => {
        const d = new Date(wb.date + 'T00:00:00')
        const dayNum = String(d.getDate()).padStart(2, '0')
        const dayName = DAY_NAMES[d.getDay()]
        return {
          day: `${dayName} ${dayNum}`,
          productive:  wb.productive,
          neutral:     wb.neutral,
          distracting: wb.distracting,
        }
      })
    }
    // Fallback while weekly data is loading
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(day + 'T00:00:00')
      d.setDate(d.getDate() - (6 - i))
      const dayNum = String(d.getDate()).padStart(2, '0')
      return { day: `${DAY_NAMES[d.getDay()]} ${dayNum}`, productive: 0, neutral: 0, distracting: 0 }
    })
  }, [weeklyBreakdowns, day])

  const circumference = 2 * Math.PI * 70
  const strokeDash = (metrics.productivity / 100) * circumference

  return (
    <div className="page-shell">
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <div className="eyebrow">Your productivity tracker</div>
          <h1>{greeting()} 👋</h1>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>
            {isToday ? `Today · Auto-refresh on (${LIVE_REFRESH_MS / 1000}s)` : `Viewing ${day}`}
            {lastUpdated && <span> · Updated {lastUpdated}</span>}
          </div>
        </div>
        <div className="page-header-right">
          {isToday && <span className="badge badge-live">Live</span>}
          <div>
            <div className="date-label">Date</div>
            <input type="date" value={day} onChange={e => onDayChange(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={onLoadToday}>Today</button>
        </div>
      </div>

      {/* Notices */}
      {message && <div className="notice">{message}</div>}
      {loading && <div className="notice">⏳ Loading data...</div>}

      {/* KPI Row */}
      <div className="kpi-grid">
        {[
          { label: 'Tracked', val: formatMinutes(metrics.totalMinutes), cls: 'kpi-tracked', valCls: '' },
          { label: 'Productive', val: formatMinutes(metrics.productive), cls: 'kpi-productive', valCls: 'kpi-productive-val' },
          { label: 'Neutral', val: formatMinutes(metrics.neutral), cls: 'kpi-neutral', valCls: 'kpi-neutral-val' },
          { label: 'Distracting', val: formatMinutes(metrics.distracting), cls: 'kpi-distracting', valCls: 'kpi-distracting-val' },
          { label: 'Idle', val: formatMinutes(metrics.idle), cls: 'kpi-idle', valCls: 'kpi-idle-val' },
        ].map(k => (
          <div key={k.label} className={`kpi-card ${k.cls}`}>
            <div className="kpi-label">{k.label}</div>
            <div className={`kpi-value ${k.valCls}`}>{k.val}</div>
          </div>
        ))}
      </div>

      {/* Main Grid: Weekly Chart + Score Panel */}
      <div className="dashboard-main-grid">
        {/* Weekly Trend Chart */}
        <div className="weekly-chart">
          <div className="chart-header">
            <div>
              <div className="chart-title">Weekly Productivity Trend</div>
              <div className="chart-subtitle">Minutes tracked per category</div>
            </div>
          </div>
          <div style={{ height: 'calc(100% - 56px)' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={weeklyData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradProd" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradNeut" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradDist" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} width={36} unit="m" />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-strong)', borderRadius: 10 }}
                  itemStyle={{ color: 'var(--text-secondary)' }}
                  labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
                  formatter={(v: number) => [`${v}m`, undefined]}
                />
                <Area type="monotone" dataKey="productive" stroke="#10b981" strokeWidth={2} fill="url(#gradProd)" name="Productive" />
                <Area type="monotone" dataKey="neutral" stroke="#3b82f6" strokeWidth={2} fill="url(#gradNeut)" name="Neutral" />
                <Area type="monotone" dataKey="distracting" stroke="#ef4444" strokeWidth={2} fill="url(#gradDist)" name="Distracting" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Productivity Score */}
        <div className="score-panel">
          <div style={{ textAlign: 'center' }}>
            <div className="chart-title" style={{ marginBottom: 4 }}>Productivity Score</div>
            <div className="chart-subtitle">Today's focus quality</div>
          </div>

          <div className="ring-container">
            <svg width="160" height="160" viewBox="0 0 160 160">
              {/* Track */}
              <circle cx="80" cy="80" r="70" fill="none" stroke="var(--bg-elevated)" strokeWidth="12" />
              {/* Progress */}
              <circle
                cx="80" cy="80" r="70"
                fill="none"
                stroke="url(#ringGrad)"
                strokeWidth="12"
                strokeLinecap="round"
                strokeDasharray={`${strokeDash} ${circumference}`}
                style={{ transition: 'stroke-dasharray 1s cubic-bezier(0.4,0,0.2,1)' }}
              />
              <defs>
                <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#10b981" />
                  <stop offset="100%" stopColor="#6366f1" />
                </linearGradient>
              </defs>
            </svg>
            <div className="ring-label">
              <div className="ring-pct">{metrics.productivity}%</div>
              <div className="ring-sub">Productive</div>
            </div>
          </div>

          {/* Breakdown Bars */}
          <div className="score-breakdown">
            {[
              { label: 'Productive', val: metrics.productive, total: metrics.totalMinutes || 1, color: '#10b981' },
              { label: 'Neutral',    val: metrics.neutral,    total: metrics.totalMinutes || 1, color: '#3b82f6' },
              { label: 'Distracting',val: metrics.distracting,total: metrics.totalMinutes || 1, color: '#ef4444' },
              { label: 'Idle',       val: metrics.idle,       total: metrics.totalMinutes || 1, color: '#6b7280' },
            ].map(row => (
              <div key={row.label}>
                <div className="score-row">
                  <div className="score-dot" style={{ background: row.color }} />
                  <div className="score-row-label">{row.label}</div>
                  <div className="score-row-val">{formatMinutes(row.val)}</div>
                </div>
                <div className="score-row-bar" style={{ width: '100%', background: 'var(--bg-elevated)', height: 4, borderRadius: 4, marginTop: 4, marginBottom: 6, overflow: 'hidden' }}>
                  <div className="score-row-bar" style={{ width: `${Math.round((row.val / row.total) * 100)}%`, background: row.color, height: '100%' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Grid: Top Apps + Summary */}
      <div className="dashboard-bottom-grid">
        {/* Top Apps */}
        <div className="top-apps-card">
          <div className="chart-header">
            <div className="chart-title">🏆 Top Applications</div>
            <div className="chart-subtitle">{metrics.switches} context switches</div>
          </div>
          <div style={{ paddingTop: 8 }}>
            {metrics.topApps.slice(0, 6).map((app, idx) => {
              const maxSec = metrics.topApps[0]?.seconds || 1
              const pct = Math.round((app.seconds / maxSec) * 100)
              return (
                <div key={idx} className="app-bar-item">
                  <div className="app-bar-label" title={app.app_name}>{app.app_name}</div>
                  <div className="app-bar-track">
                    <div className="app-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                  <div className="app-bar-val">{app.display}</div>
                </div>
              )
            })}
            {metrics.topApps.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
                No app activity tracked yet
              </div>
            )}
          </div>
        </div>

        {/* Day Summary */}
        <div className="day-summary-card">
          <div>
            <div className="chart-title">📝 Day Summary</div>
          </div>
          <p className="summary-text">
            {dashboard?.summary ?? 'No activity recorded yet. Open some apps and the tracker will start recording your activity.'}
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 'auto' }}>
            {[
              { label: 'Score', val: `${metrics.productivity}%`, color: 'var(--accent)' },
              { label: 'Focus', val: formatMinutes(metrics.productive), color: 'var(--green)' },
              { label: 'Switches', val: String(metrics.switches), color: 'var(--text-muted)' },
            ].map(stat => (
              <div key={stat.label} style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 10, padding: '10px 16px', minWidth: 80 }}>
                <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>{stat.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: stat.color, letterSpacing: '-0.03em' }}>{stat.val}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
