import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TopAppItem } from '../types'

type Props = {
  items: TopAppItem[]
}

export function TopAppsChart({ items }: Props) {
  const maxMs = items.reduce((max, item) => Math.max(max, item.seconds * 1000), 0)
  const isHours = maxMs >= 3600000
  const divisor = isHours ? 3600 : 60
  const unitLabel = isHours ? 'Hours' : 'Minutes'

  const data = items.map((item) => ({
    name: item.app_name,
    value: Number((item.seconds / divisor).toFixed(isHours ? 2 : 0)),
  }))

  return (
    <div className="card chart-card">
      <h3>Top apps</h3>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" label={{ value: 'Application', position: 'insideBottom', offset: -10 }} />
            <YAxis label={{ value: unitLabel, angle: -90, position: 'insideLeft', offset: 0 }} />
            <Tooltip formatter={(value: number) => [`${value} ${unitLabel}`, undefined]} />
            <Bar dataKey="value" fill="#111827" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
