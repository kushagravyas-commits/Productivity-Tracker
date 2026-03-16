import { useMemo } from 'react'
import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from 'recharts'
import { TimelineItem } from '../types'

interface ProductivityPieProps {
  items: TimelineItem[]
}

const COLORS = {
  productive: '#166534',
  neutral: '#075985',
  distracting: '#991b1b',
}

export default function ProductivityPie({ items }: ProductivityPieProps) {
  const data = useMemo(() => {
    const categoryTotals: Record<string, number> = {
      productive: 0,
      neutral: 0,
      distracting: 0,
    }

    items.forEach((item) => {
      const startDate = new Date(item.started_at)
      const endDate = new Date(item.ended_at)
      const seconds = (endDate.getTime() - startDate.getTime()) / 1000
      const category = item.productivity_label || 'neutral'
      categoryTotals[category] = (categoryTotals[category] || 0) + seconds
    })

    const total = Object.values(categoryTotals).reduce((a, b) => a + b, 0)

    if (total === 0) {
      return [{ name: 'No Data', value: 1 }]
    }

    return [
      {
        name: 'Productive',
        value: Math.round((categoryTotals['productive'] / total) * 100),
      },
      {
        name: 'Neutral',
        value: Math.round((categoryTotals['neutral'] / total) * 100),
      },
      {
        name: 'Distracting',
        value: Math.round((categoryTotals['distracting'] / total) * 100),
      },
    ].filter((item) => item.value > 0)
  }, [items])

  return (
    <div className="chart-wrap card">
      <h3>Productivity Breakdown</h3>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, value }) => `${name} ${value}%`}
            outerRadius={80}
            fill="#8884d8"
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={COLORS[entry.name.toLowerCase() as keyof typeof COLORS] || '#8884d8'}
              />
            ))}
          </Pie>
          <Tooltip formatter={(value) => `${value}%`} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
