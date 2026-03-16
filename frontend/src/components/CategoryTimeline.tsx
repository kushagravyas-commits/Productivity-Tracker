import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TimelineItem } from '../types'

interface CategoryTimelineProps {
  items: TimelineItem[]
}

export default function CategoryTimeline({ items }: CategoryTimelineProps) {
  const data = useMemo(() => {
    const hourData: Record<
      string,
      { productive: number; neutral: number; distracting: number; idle: number }
    > = {}

    let totalDayMs = 0

    items.forEach((item) => {
      const startDate = new Date(item.started_at)
      const endDate = new Date(item.ended_at)
      const hour = startDate.getHours()
      const hourKey = `${String(hour).padStart(2, '0')}:00`

      const ms = Math.max(0, endDate.getTime() - startDate.getTime())
      totalDayMs += ms
      const category = item.productivity_label || 'neutral'

      if (!hourData[hourKey]) {
        hourData[hourKey] = { productive: 0, neutral: 0, distracting: 0, idle: 0 }
      }

      if (category in hourData[hourKey]) {
        hourData[hourKey][category as keyof typeof hourData[string]] += ms
      }
    })

    const chartData = []
    for (let h = 0; h < 24; h++) {
      const hourKey = `${String(h).padStart(2, '0')}:00`
      const raw = hourData[hourKey] || { productive: 0, neutral: 0, distracting: 0, idle: 0 }

      chartData.push({
        hour: hourKey,
        raw
      })
    }

    const isHours = totalDayMs >= 3600000
    const divisor = isHours ? 3600000 : 60000
    const unitLabel = isHours ? 'Hours' : 'Minutes'

    const finalData = chartData.map(d => ({
      hour: d.hour,
      productive: Number((d.raw.productive / divisor).toFixed(isHours ? 2 : 0)),
      neutral: Number((d.raw.neutral / divisor).toFixed(isHours ? 2 : 0)),
      distracting: Number((d.raw.distracting / divisor).toFixed(isHours ? 2 : 0)),
      idle: Number((d.raw.idle / divisor).toFixed(isHours ? 2 : 0)),
    }))

    return { finalData, unitLabel }
  }, [items])

  return (
    <div className="chart-wrap card">
      <h3>Productivity Distribution (Hourly)</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data.finalData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="hour" label={{ value: 'Time (Hour)', position: 'insideBottom', offset: -10 }} />
          <YAxis label={{ value: data.unitLabel, angle: -90, position: 'insideLeft', offset: 0 }} />
          <Tooltip formatter={(value: number) => [`${value} ${data.unitLabel}`, undefined]} />
          <Legend />
          <Bar dataKey="productive" stackId="a" fill="#166534" />
          <Bar dataKey="neutral" stackId="a" fill="#075985" />
          <Bar dataKey="distracting" stackId="a" fill="#991b1b" />
          <Bar dataKey="idle" stackId="a" fill="#9ca3af" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
