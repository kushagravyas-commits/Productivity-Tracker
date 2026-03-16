import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import type { TimelineItem } from '../types'

interface Props { items: TimelineItem[] }

export default function ProductivityTrendLine({ items }: Props) {
  const { data, unit } = useMemo(() => {
    const hourData: Record<string, { productive: number; total: number }> = {}
    let totalMs = 0

    items.forEach(item => {
      const h = new Date(item.started_at).getHours()
      const key = `${String(h).padStart(2, '0')}:00`
      const ms = Math.max(0, new Date(item.ended_at).getTime() - new Date(item.started_at).getTime())
      totalMs += ms
      if (!hourData[key]) hourData[key] = { productive: 0, total: 0 }
      hourData[key].total += ms
      if (item.productivity_label === 'productive') hourData[key].productive += ms
    })

    const isHours = totalMs >= 3600000
    const divisor = isHours ? 3600000 : 60000
    const unit = isHours ? 'hrs' : 'min'

    const chartData = Array.from({ length: 24 }, (_, h) => {
      const key = `${String(h).padStart(2, '0')}:00`
      const raw = hourData[key]
      return {
        hour: key,
        score: raw ? Math.round((raw.productive / raw.total) * 100) : 0,
        tracked: +((raw?.total || 0) / divisor).toFixed(2),
      }
    })

    return { data: chartData, unit }
  }, [items])

  const tooltipStyle = { background: 'var(--bg-elevated)', border: '1px solid var(--border-strong)', borderRadius: 10 }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="hour" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} interval={3} />
        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} width={32} unit="%" domain={[0, 100]} />
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
          formatter={(v: number) => [`${v}%`, 'Productivity Score']}
        />
        <Bar dataKey="score" fill="url(#barGrad)" radius={[4, 4, 0, 0]} name="Score" maxBarSize={24} />
      </BarChart>
    </ResponsiveContainer>
  )
}
