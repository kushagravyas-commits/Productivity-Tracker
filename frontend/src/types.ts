export type KPI = {
  label: string
  value_seconds: number
  display: string
}

export type TopAppItem = {
  app_name: string
  seconds: number
  display: string
}

export type TimelineItem = {
  started_at: string
  ended_at: string
  app_name: string
  window_title?: string | null
  productivity_label: 'productive' | 'neutral' | 'distracting'
}

export type ProductivityBreakdown = {
  productive: number
  neutral: number
  distracting: number
  idle: number
}

export type DashboardResponse = {
  day: string
  kpis: KPI[]
  top_apps: TopAppItem[]
  timeline: TimelineItem[]
  summary: string
  productivity_breakdown: ProductivityBreakdown
}

export type SessionItem = {
  started_at: string
  ended_at: string
  duration_seconds: number
  summary: string
  top_apps: TopAppItem[]
}

export type HistoryResponse = {
  day: string
  sessions: SessionItem[]
  day_summary: string
}
