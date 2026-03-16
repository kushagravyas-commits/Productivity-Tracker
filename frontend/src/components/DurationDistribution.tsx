import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TimelineItem } from '../types'

interface DurationDistributionProps {
  items: TimelineItem[]
}

export default function DurationDistribution({ items }: DurationDistributionProps) {
  const data = useMemo(() => {
    const bins = {
      '0-5m': 0,
      '5-10m': 0,
      '10-20m': 0,
      '20-60m': 0,
      '60m+': 0,
    }

    items.forEach((item) => {
      const startDate = new Date(item.started_at)
      const endDate = new Date(item.ended_at)
      
      const ms = Math.max(0, endDate.getTime() - startDate.getTime())
      const minutes = ms / 60000

      if (minutes < 5) bins['0-5m']++
      else if (minutes < 10) bins['5-10m']++
      else if (minutes < 20) bins['10-20m']++
      else if (minutes < 60) bins['20-60m']++
      else bins['60m+']++
    })

    return [
      { range: '0-5m', count: bins['0-5m'] },
      { range: '5-10m', count: bins['5-10m'] },
      { range: '10-20m', count: bins['10-20m'] },
      { range: '20-60m', count: bins['20-60m'] },
      { range: '60m+', count: bins['60m+'] },
    ].filter((item) => item.count > 0)
  }, [items])

  if (data.length === 0) {
    return (
      <div className="chart-wrap card">
        <h3>Activity Duration Distribution</h3>
        <p style={{ textAlign: 'center', opacity: 0.7 }}>No data to display</p>
      </div>
    )
  }

  return (
    <div className="chart-wrap card">
      <h3>Activity Duration Distribution</h3>
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="range" label={{ value: 'Duration Range', position: 'insideBottom', offset: -10 }} />
          <YAxis label={{ value: 'Activity Count', angle: -90, position: 'insideLeft', offset: 0 }} />
          <Tooltip />
          <Bar dataKey="count" fill="#6366f1" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
