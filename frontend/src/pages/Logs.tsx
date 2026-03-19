import { useMemo, useState } from 'react'
import CategoryTrendLine from '../components/CategoryTrendLine'
import AppTrendLine from '../components/AppTrendLine'
import AppUsagePie from '../components/AppUsagePie'
import DurationDistribution from '../components/DurationDistribution'
import ProductivityTrendLine from '../components/ProductivityTrendLine'
import ActivityTimeline from '../components/ActivityTimeline'
import LogTable from '../components/LogTable'
import type { DashboardResponse, TimelineItem } from '../types'

export interface FilterState {
  appName: string | null
  category: 'productive' | 'neutral' | 'distracting' | 'idle' | null
  searchQuery: string
}

interface LogsPageProps {
  day: string
  dashboard: DashboardResponse | null
  loading: boolean
  message: string
  onDayChange: (day: string) => void
  onLoadToday: () => void
  onRefresh: () => void
}

type SortBy = 'time' | 'duration' | 'app'
type SortOrder = 'asc' | 'desc'

export default function Logs({ day, dashboard, loading, message, onDayChange, onLoadToday, onRefresh }: LogsPageProps) {
  const [filters, setFilters] = useState<FilterState>({ appName: null, category: null, searchQuery: '' })
  const [sortBy, setSortBy] = useState<SortBy>('time')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')

  const uniqueApps = useMemo(() => {
    if (!dashboard?.timeline) return []
    return Array.from(new Set(dashboard.timeline.map(i => i.app_name))).sort()
  }, [dashboard?.timeline])

  const filteredEvents = useMemo((): TimelineItem[] => {
    if (!dashboard?.timeline) return []
    return dashboard.timeline.filter(item => {
      if (filters.appName && item.app_name !== filters.appName) return false
      if (filters.category && item.productivity_label !== filters.category) return false
      if (filters.searchQuery && !(item.window_title?.toLowerCase() || '').includes(filters.searchQuery.toLowerCase())) return false
      return true
    })
  }, [dashboard?.timeline, filters])

  const sortedEvents = useMemo(() => {
    const s = [...filteredEvents]
    if (sortBy === 'time') s.sort((a, b) => a.started_at.localeCompare(b.started_at))
    else if (sortBy === 'duration') s.sort((a, b) => (new Date(a.ended_at).getTime() - new Date(a.started_at).getTime()) - (new Date(b.ended_at).getTime() - new Date(b.started_at).getTime()))
    else if (sortBy === 'app') s.sort((a, b) => a.app_name.localeCompare(b.app_name))
    if (sortOrder === 'desc') s.reverse()
    return s
  }, [filteredEvents, sortBy, sortOrder])

  const categories: Array<'productive' | 'neutral' | 'distracting' | 'idle'> = ['productive', 'neutral', 'distracting', 'idle']
  const catColors: Record<string, string> = { productive: 'var(--green)', neutral: 'var(--blue)', distracting: 'var(--red)', idle: 'var(--gray)' }

  return (
    <div className="page-shell">
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <div className="eyebrow">Activity Analytics</div>
          <h1>Logs & Analytics</h1>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>Deep-dive into your productivity patterns</div>
        </div>
        <div className="page-header-right">
          <div>
            <div className="date-label">Date</div>
            <input type="date" value={day} onChange={e => onDayChange(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={onLoadToday}>Today</button>
          <button className="btn-refresh" onClick={onRefresh} title="Refresh data">↻</button>
        </div>
      </div>

      {message && <div className="notice">{message}</div>}
      {loading && <div className="notice">⏳ Loading data...</div>}

      {/* Filter Bar */}
      <div className="filter-bar">
        {/* Search */}
        <div className="filter-search">
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>🔍</span>
          <input
            type="text"
            placeholder="Search window titles..."
            value={filters.searchQuery}
            onChange={e => setFilters(f => ({ ...f, searchQuery: e.target.value }))}
          />
        </div>

        <div className="filter-divider" />

        {/* Category filters */}
        <div className="filter-group">
          {categories.map(cat => (
            <button
              key={cat}
              className={`filter-pill ${filters.category === cat ? 'active' : ''}`}
              onClick={() => setFilters(f => ({ ...f, category: f.category === cat ? null : cat }))}
              style={filters.category === cat ? { borderColor: catColors[cat], color: catColors[cat] } : {}}
            >
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: catColors[cat], display: 'inline-block' }} />
              {cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>

        <div className="filter-divider" />

        {/* App filter */}
        <select
          className="sort-select"
          value={filters.appName || ''}
          onChange={e => setFilters(f => ({ ...f, appName: e.target.value || null }))}
        >
          <option value="">All Apps</option>
          {uniqueApps.map(app => <option key={app} value={app}>{app}</option>)}
        </select>

        {/* Sort */}
        <select className="sort-select" value={`${sortBy}-${sortOrder}`} onChange={e => {
          const [by, ord] = e.target.value.split('-') as [SortBy, SortOrder]
          setSortBy(by); setSortOrder(ord)
        }}>
          <option value="time-asc">Time ↑</option>
          <option value="time-desc">Time ↓</option>
          <option value="duration-desc">Duration ↓</option>
          <option value="duration-asc">Duration ↑</option>
          <option value="app-asc">App A-Z</option>
        </select>

        {/* Clear */}
        {(filters.appName || filters.category || filters.searchQuery) && (
          <button className="btn btn-ghost" style={{ color: 'var(--red)', fontSize: 12 }}
            onClick={() => setFilters({ appName: null, category: null, searchQuery: '' })}>
            ✕ Clear
          </button>
        )}
      </div>

      {/* Charts Grid */}
      <div className="charts-grid">
        <div className="chart-wrap">
          <div className="chart-header" style={{ marginBottom: 12 }}>
            <div className="chart-title">📊 Category Trend</div>
            <div className="chart-subtitle">Hourly breakdown</div>
          </div>
          <div style={{ height: 'calc(100% - 52px)' }}>
            <CategoryTrendLine items={filteredEvents} />
          </div>
        </div>

        <div className="chart-wrap">
          <div className="chart-header" style={{ marginBottom: 12 }}>
            <div className="chart-title">📱 App Trend</div>
            <div className="chart-subtitle">Top apps over time</div>
          </div>
          <div style={{ height: 'calc(100% - 52px)' }}>
            <AppTrendLine items={filteredEvents} />
          </div>
        </div>

        <div className="chart-wrap">
          <div className="chart-header" style={{ marginBottom: 12 }}>
            <div className="chart-title">🥧 App Distribution</div>
            <div className="chart-subtitle">By time spent</div>
          </div>
          <div style={{ height: 'calc(100% - 52px)' }}>
            <AppUsagePie items={filteredEvents} />
          </div>
        </div>

        <div className="chart-wrap">
          <div className="chart-header" style={{ marginBottom: 12 }}>
            <div className="chart-title">⏱️ Productivity Trend</div>
            <div className="chart-subtitle">Hourly scoring</div>
          </div>
          <div style={{ height: 'calc(100% - 52px)' }}>
            <ProductivityTrendLine items={filteredEvents} />
          </div>
        </div>
      </div>

      {/* Activity Timeline */}
      <div className="chart-wrap" style={{ height: 'auto', marginBottom: 16 }}>
        <div className="chart-header" style={{ marginBottom: 12 }}>
          <div className="chart-title">🕒 Activity Timeline</div>
          <div className="chart-subtitle">Visual time blocks</div>
        </div>
        <div style={{ height: 300 }}>
          <ActivityTimeline items={filteredEvents} />
        </div>
      </div>

      {/* Log Table */}
      <div className="log-section">
        <div className="log-section-header">
          <div>
            <div className="chart-title">📋 Detailed Logs</div>
            <div className="chart-subtitle" style={{ marginTop: 2 }}>{sortedEvents.length} entries</div>
          </div>
          <div className="badge" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
            {sortedEvents.length} rows
          </div>
        </div>
        {sortedEvents.length > 0 ? (
          <LogTable
            items={sortedEvents}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={(by, ord) => { setSortBy(by as SortBy); setSortOrder(ord as SortOrder) }}
          />
        ) : (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
            No activities match your filters.
          </div>
        )}
      </div>
    </div>
  )
}
