import { useMemo } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { TimelineItem } from '../types'

interface Props { items: TimelineItem[] }

export default function CategoryTrendLine({ items }: Props) {
  const { data, unit } = useMemo(() => {
    const hourData: Record<string, Record<string, number>> = {}
    let totalMs = 0

    items.forEach(item => {
      const h = new Date(item.started_at).getHours()
      const key = `${String(h).padStart(2, '0')}:00`
      const ms = Math.max(0, new Date(item.ended_at).getTime() - new Date(item.started_at).getTime())
      totalMs += ms
      if (!hourData[key]) hourData[key] = { productive: 0, neutral: 0, distracting: 0, idle: 0 }
      const cat = item.productivity_label || 'neutral'
      if (cat in hourData[key]) hourData[key][cat] += ms
    })

    const isHours = totalMs >= 3600000
    const divisor = isHours ? 3600000 : 60000
    const unit = isHours ? 'hrs' : 'min'

    const chartData = Array.from({ length: 24 }, (_, h) => {
      const key = `${String(h).padStart(2, '0')}:00`
      const raw = hourData[key] || {}
      return {
        hour: key,
        productive: +((raw.productive || 0) / divisor).toFixed(2),
        neutral:    +((raw.neutral    || 0) / divisor).toFixed(2),
        distracting:+((raw.distracting|| 0) / divisor).toFixed(2),
        idle:       +((raw.idle       || 0) / divisor).toFixed(2),
      }
    })

    return { data: chartData, unit }
  }, [items])

  const tooltipStyle = { background: 'var(--bg-elevated)', border: '1px solid var(--border-strong)', borderRadius: 10 }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          {[
            ['prod', '#10b981'], ['neut', '#3b82f6'], ['dist', '#ef4444'], ['idle', '#6b7280']
          ].map(([id, color]) => (
            <linearGradient key={id} id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="hour" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} interval={3} />
        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} width={32} unit={unit} />
        <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }} formatter={(v: number) => [`${v} ${unit}`, undefined]} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
        <Area type="monotone" dataKey="productive" stroke="#10b981" strokeWidth={2} fill="url(#g-prod)" name="Productive" />
        <Area type="monotone" dataKey="neutral"    stroke="#3b82f6" strokeWidth={2} fill="url(#g-neut)" name="Neutral" />
        <Area type="monotone" dataKey="distracting"stroke="#ef4444" strokeWidth={2} fill="url(#g-dist)" name="Distracting" />
        <Area type="monotone" dataKey="idle"       stroke="#6b7280" strokeWidth={1.5} fill="url(#g-idle)" name="Idle" />
      </AreaChart>
    </ResponsiveContainer>
  )
}
