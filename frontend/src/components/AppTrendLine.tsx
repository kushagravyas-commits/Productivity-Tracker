import { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { TimelineItem } from '../types'

interface Props { items: TimelineItem[] }

export default function AppTrendLine({ items }: Props) {
  const { data, topApps, unit } = useMemo(() => {
    const appHour: Record<string, Record<string, number>> = {}
    let totalMs = 0

    items.forEach(item => {
      const h = new Date(item.started_at).getHours()
      const key = `${String(h).padStart(2, '0')}:00`
      const ms = Math.max(0, new Date(item.ended_at).getTime() - new Date(item.started_at).getTime())
      totalMs += ms
      if (!appHour[item.app_name]) appHour[item.app_name] = {}
      appHour[item.app_name][key] = (appHour[item.app_name][key] || 0) + ms
    })

    const isHours = totalMs >= 3600000
    const divisor = isHours ? 3600000 : 60000
    const unit = isHours ? 'hrs' : 'min'

    const totals = Object.entries(appHour).map(([app, hours]) => ({ app, total: Object.values(hours).reduce((a, b) => a + b, 0) }))
    const topApps = totals.sort((a, b) => b.total - a.total).slice(0, 5).map(a => a.app)

    const chartData = Array.from({ length: 24 }, (_, h) => {
      const key = `${String(h).padStart(2, '0')}:00`
      const row: Record<string, number | string> = { hour: key }
      topApps.forEach(app => {
        row[app] = +((appHour[app]?.[key] || 0) / divisor).toFixed(2)
      })
      return row
    })

    return { data: chartData, topApps, unit }
  }, [items])

  const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
  const tooltipStyle = { background: 'var(--bg-elevated)', border: '1px solid var(--border-strong)', borderRadius: 10 }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="hour" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} interval={3} />
        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} width={32} unit={unit} />
        <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }} formatter={(v: number) => [`${v} ${unit}`, undefined]} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
        {topApps.map((app, i) => (
          <Line key={app} type="monotone" dataKey={app} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} name={app} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
