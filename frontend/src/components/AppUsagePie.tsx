import { useMemo } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { TimelineItem } from '../types'

interface Props { items: TimelineItem[] }

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#3b82f6', '#ec4899', '#14b8a6']

export default function AppUsagePie({ items }: Props) {
  const data = useMemo(() => {
    const secs: Record<string, number> = {}
    items.forEach(item => {
      const d = Math.max(0, new Date(item.ended_at).getTime() - new Date(item.started_at).getTime()) / 1000
      secs[item.app_name] = (secs[item.app_name] || 0) + d
    })
    return Object.entries(secs)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 8)
      .map(([name, value]) => ({
        name,
        value: Math.round(value / 60),
        display: value >= 3600 ? `${(value / 3600).toFixed(1)}h` : `${Math.round(value / 60)}m`,
      }))
  }, [items])

  const tooltipStyle = { background: 'var(--bg-elevated)', border: '1px solid var(--border-strong)', borderRadius: 10 }

  if (data.length === 0) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: 13 }}>
      No data
    </div>
  )

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={data}
          cx="40%"
          cy="50%"
          innerRadius="45%"
          outerRadius="70%"
          paddingAngle={3}
          dataKey="value"
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="none" />
          ))}
        </Pie>
        <Tooltip
          contentStyle={tooltipStyle}
          labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
          formatter={(v: number, name: string) => {
            const item = data.find(d => d.name === name)
            return [item?.display ?? `${v}m`, name]
          }}
        />
        <Legend
          layout="vertical"
          align="right"
          verticalAlign="middle"
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 11, lineHeight: '22px' }}
          formatter={(value) => <span style={{ color: 'var(--text-secondary)' }}>{value}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
